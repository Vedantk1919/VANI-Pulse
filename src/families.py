"""Model families with a common fit / predict / save / load interface.

Used by model.py (production ensemble) and compare_models.py (bake-off).
"""

import lightgbm as lgb
import pandas as pd
import xgboost as xgb
from catboost import CatBoostClassifier, Pool
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .features import FEATURES, NUM_FEATURES, CAT_FEATURES

LGB_PARAMS = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200,
                  feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0,
                  cat_smooth=50, verbose=-1, num_threads=8, seed=7, deterministic=True, force_row_wise=True)
XGB_PARAMS = dict(objective="binary:logistic", eval_metric="logloss", tree_method="hist", eta=0.05, max_depth=7,
                  min_child_weight=50, subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, max_cat_to_onehot=1,
                  nthread=8, seed=7)
CAT_PARAMS = dict(loss_function="Logloss", learning_rate=0.08, depth=7, l2_leaf_reg=5, thread_count=8,
                  random_seed=7, verbose=False, allow_writing_files=False)


def to_frame(X, levels):
    """Feature frame with categoricals fixed to the training category levels."""
    X = X[FEATURES].copy()
    for c in CAT_FEATURES:
        X[c] = pd.Categorical(X[c].astype(str), categories=levels[c])
    return X


def str_cats(X):
    X = X[FEATURES].copy()
    for c in CAT_FEATURES:
        X[c] = X[c].astype(str)
    return X


class LGBM:
    name, ext = "lightgbm", "txt"

    def fit(self, fit, val, y, levels):
        self.levels = levels
        dtr = lgb.Dataset(to_frame(fit, levels), fit[y], categorical_feature=CAT_FEATURES)
        dva = lgb.Dataset(to_frame(val, levels), val[y], categorical_feature=CAT_FEATURES)
        m = lgb.train(LGB_PARAMS, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
        tr = pd.concat([fit, val])
        self.m = lgb.train(LGB_PARAMS, lgb.Dataset(to_frame(tr, levels), tr[y], categorical_feature=CAT_FEATURES),
                           m.best_iteration)
        return self

    def predict(self, X):
        return self.m.predict(to_frame(X, self.levels))

    def importance(self):
        return pd.Series(self.m.feature_importance("gain"), index=FEATURES)

    def save(self, path):
        self.m.save_model(str(path))

    def load(self, path, levels):
        self.m, self.levels = lgb.Booster(model_file=str(path)), levels
        return self


class XGB:
    name, ext = "xgboost", "json"

    def fit(self, fit, val, y, levels):
        self.levels = levels
        dtr = xgb.DMatrix(to_frame(fit, levels), fit[y], enable_categorical=True)
        dva = xgb.DMatrix(to_frame(val, levels), val[y], enable_categorical=True)
        m = xgb.train(XGB_PARAMS, dtr, 2000, evals=[(dva, "val")], early_stopping_rounds=100, verbose_eval=False)
        tr = pd.concat([fit, val])
        self.m = xgb.train(XGB_PARAMS, xgb.DMatrix(to_frame(tr, levels), tr[y], enable_categorical=True),
                           m.best_iteration + 1)
        return self

    def predict(self, X):
        return self.m.predict(xgb.DMatrix(to_frame(X, self.levels), enable_categorical=True))

    def importance(self):
        g = self.m.get_score(importance_type="total_gain")
        return pd.Series({f: g.get(f, 0.0) for f in FEATURES})

    def save(self, path):
        self.m.save_model(str(path))

    def load(self, path, levels):
        self.m, self.levels = xgb.Booster(), levels
        self.m.load_model(str(path))
        return self


class Cat:
    name, ext = "catboost", "cbm"

    def fit(self, fit, val, y, levels):
        m = CatBoostClassifier(iterations=2000, od_type="Iter", od_wait=100, **CAT_PARAMS)
        m.fit(Pool(str_cats(fit), fit[y], cat_features=CAT_FEATURES),
              eval_set=Pool(str_cats(val), val[y], cat_features=CAT_FEATURES))
        tr = pd.concat([fit, val])
        self.m = CatBoostClassifier(iterations=max(m.get_best_iteration(), 50), **CAT_PARAMS)
        self.m.fit(Pool(str_cats(tr), tr[y], cat_features=CAT_FEATURES))
        return self

    def predict(self, X):
        return self.m.predict_proba(Pool(str_cats(X), cat_features=CAT_FEATURES))[:, 1]

    def importance(self):
        return pd.Series(self.m.get_feature_importance(), index=FEATURES)

    def save(self, path):
        self.m.save_model(str(path))

    def load(self, path, levels):
        self.m = CatBoostClassifier()
        self.m.load_model(str(path))
        return self


class LogReg:
    name, ext = "logistic_regression", None

    def fit(self, fit, val, y, levels):
        pre = ColumnTransformer([
            ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()),
             NUM_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=200), CAT_FEATURES)])
        self.m = make_pipeline(pre, LogisticRegression(C=0.5, max_iter=1000))
        tr = pd.concat([fit, val])
        self.m.fit(str_cats(tr), tr[y])
        return self

    def predict(self, X):
        return self.m.predict_proba(str_cats(X))[:, 1]


class Ensemble:
    """Average of the members' probabilities."""
    name = "ensemble"

    def __init__(self, members):
        self.members = members

    def predict(self, X):
        return sum(m.predict(X) for m in self.members) / len(self.members)


ALL = {"logistic_regression": LogReg, "lightgbm": LGBM, "xgboost": XGB, "catboost": Cat}
ENSEMBLE_MEMBERS = (LGBM, XGB, Cat)
