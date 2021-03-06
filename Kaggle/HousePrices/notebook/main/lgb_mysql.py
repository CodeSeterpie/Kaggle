# -*- coding: utf-8 -*-
# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.4.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
import os
import datetime
import itertools as itr
import numpy as np
import pandas as pd
import seaborn as sns
import lightgbm as lgb
import xgboost as xgb
import sqlalchemy as sql
import matplotlib as plt
from sklearn.model_selection import KFold
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_squared_error
from sklearn.ensemble import RandomForestRegressor

# プログレスバーの表示に使用
from tqdm.notebook import tqdm
# 警告を非表示に設定
import warnings
warnings.filterwarnings('ignore')


def printTime(tag):
    """
    ログ出力用の関数

    """
    print(tag + ':', datetime.datetime.now())


printTime('Inputファイルを表示')
for dirname, _, filenames in os.walk('/kaggle/input'):
    for filename in filenames:
        print(os.path.join(dirname, filename))

# %% [markdown]
# ### データベースの接続設定

# %%
# データベースの接続設定
#   Connect Stringは下の形式で記述する(mysql+pymysqlはmysqlにPyMySQLライブラリを使ってアクセスするという意味)
#   mysql+pymysql://<username>:<password>@<host>/<dbname>[?<options>]
connect = 'mysql+pymysql://docker:docker@houseprices_mysql/kaggle'
engine = sql.create_engine(connect, echo=False)

# %% [markdown]
# #### 学習データの読み込み

# %%
train = pd.read_csv('/kaggle/input/train.csv')
test = pd.read_csv('/kaggle/input/test.csv')

# データベースに学習データ、テストデータを格納（Dataframeのindexはカラムに含めず、テーブル自体を上書き）
train.to_sql('train', engine, index=False, if_exists='replace')
test.to_sql('test', engine, index=False, if_exists='replace')


# %% [markdown]
# #### 欠損地を穴埋め

# %%
def missing_percentage(df):
    """This function takes a DataFrame(df) as input and returns two columns, total missing values and total missing values percentage"""
    ## the two following line may seem complicated but its actually very simple. 
    total = df.isnull().sum().sort_values(ascending = False)[df.isnull().sum().sort_values(ascending = False) != 0]
    percent = round(df.isnull().sum().sort_values(ascending = False)/len(df)*100,2)[round(df.isnull().sum().sort_values(ascending = False)/len(df)*100,2) != 0]
    return pd.concat([total, percent], axis=1, keys=['Total','Percent'])


all_data = train.copy()
all_data = all_data.append(test, ignore_index=True)

missing_val_col = ["Alley",
                   "PoolQC",
                   "MiscFeature",
                   "Fence",
                   "FireplaceQu",
                   "GarageType",
                   "GarageFinish",
                   "GarageQual",
                   "GarageCond",
                   'BsmtQual',
                   'BsmtCond',
                   'BsmtExposure',
                   'BsmtFinType1',
                   'BsmtFinType2',
                   'MasVnrType']

for i in missing_val_col:
    train[i] = train[i].fillna('None')
    test[i] = test[i].fillna('None')

missing_val_col2 = ['BsmtFinSF1',
                    'BsmtFinSF2',
                    'BsmtUnfSF',
                    'TotalBsmtSF',
                    'BsmtFullBath', 
                    'BsmtHalfBath', 
                    'GarageYrBlt',
                    'GarageArea',
                    'GarageCars',
                    'MasVnrArea']

for i in missing_val_col2:
    train[i] = train[i].fillna(0)
    test[i] = test[i].fillna(0)
        
train['Functional'] = train['Functional'].fillna('Typ')
test['Functional'] = test['Functional'].fillna('Typ')

train['Utilities'] = train['Utilities'].fillna('AllPub')
test['Utilities'] = test['Utilities'].fillna('AllPub')

train['Electrical'] = train['Electrical'].fillna("SBrkr")
test['Electrical'] = test['Electrical'].fillna("SBrkr")

train['KitchenQual'] = train['KitchenQual'].fillna("TA")
test['KitchenQual'] = test['KitchenQual'].fillna("TA")

"""
all_data['LotFrontage'] = all_data.groupby('Neighborhood')['LotFrontage'].transform( lambda x: x.fillna(x.mean()))
train['LotFrontage'] = all_data['LotFrontage'][0:len(train)]
test['LotFrontage'] = pd.Series(all_data['LotFrontage'][len(train): len(train) + len(test) + 1].values.tolist())
"""
train['LotFrontage'] = train['LotFrontage'].fillna(0)
test['LotFrontage'] = test['LotFrontage'].fillna(0)

"""
all_data['MSZoning'] = all_data.groupby('MSSubClass')['MSZoning'].transform(lambda x: x.fillna(x.mode()[0]))
train['MSZoning'] = all_data['MSZoning'][0:len(train)]
test['MSZoning'] = pd.Series(all_data['MSZoning'][len(train): len(train) + len(test) + 1].values.tolist())
"""
train['MSZoning'] = train['MSZoning'].fillna('None')
test['MSZoning'] = test['MSZoning'].fillna('None')


# 学習データ、テストデータ合わせた中での最頻値を設定
train['Exterior1st'] = train['Exterior1st'].fillna(all_data['Exterior1st'].mode()[0])
test['Exterior1st'] = test['Exterior1st'].fillna(all_data['Exterior1st'].mode()[0])

train['Exterior2nd'] = train['Exterior2nd'].fillna(all_data['Exterior2nd'].mode()[0])
test['Exterior2nd'] = test['Exterior2nd'].fillna(all_data['Exterior2nd'].mode()[0])

train['SaleType'] = train['SaleType'].fillna(all_data['SaleType'].mode()[0])
test['SaleType'] = test['SaleType'].fillna(all_data['SaleType'].mode()[0])


    
#missing_percentage(train)
missing_percentage(test)

# %% [markdown]
#  #### 特徴量作成

# %%
# 解析対象とする数値列を設定
targets_num = ['1stFlrSF',
               '2ndFlrSF',
               'BsmtFinSF1',
               'Fireplaces',
               'FullBath',
               'GarageArea',
               'GarageCars',
               'GarageYrBlt',
               'GrLivArea',
               'MasVnrArea',
               'OverallQual',
               'OverallCond',
               'TotalBsmtSF',
               'TotRmsAbvGrd',
               'YearBuilt',
               'YearRemodAdd',
               # ここからカテゴリ変数を数値変換した変数
               'LotShape',
               'BsmtCond',
               'BsmtQual',
               'FireplaceQu',
               'KitchenQual',
               # 'PoolQC',
               'GarageQual',
               'MasVnrType'
               ]

# 解析対象とするカテゴリ列を設定
targets_category = [
    'MSSubClass',
    'MSZoning',
    # 'Street',
    'Alley',
    # 'LotShape',
    'LandContour',
    # 'Utilities',
    'LotConfig',
    'LandSlope',
    'Neighborhood',
    'Condition1',
    'Condition2',
    'BldgType',
    'HouseStyle',
    'RoofStyle',
    'RoofMatl',
    'Exterior1st',
    'Exterior2nd',
    # 'MasVnrType',
    'ExterQual',
    'ExterCond',
    'Foundation',
    # 'BsmtQual',
    # 'BsmtCond',
    'BsmtExposure',
    'BsmtFinType1',
    'BsmtFinType2',
    'Heating',
    'HeatingQC',
    'CentralAir',
    'Electrical',
    # 'KitchenQual',
    'Functional',
    # 'FireplaceQu',
    'GarageType',
    'GarageFinish',
    # 'GarageQual',
    'GarageCond',
    'PavedDrive',
    # 'PoolQC',
    'Fence',
    'MiscFeature',
    'SaleType',
    'SaleCondition']

# 解析対象とする数値列とカテゴリ列の列名を連結
targets = targets_num.copy()
targets.extend(targets_category)

# Dataframeの列の型がobjectのままだとLabelEncoderでエラーするため、strに変換
# ※変換処理後にinfo()で型を確認しても、objectと表示されるが内部的にはstrに変換されている。
train[targets_category] = train[targets_category].astype(str)
test[targets_category] = test[targets_category].astype(str)

# %%
train = train.drop(['Utilities', 'Street', 'PoolQC',], axis=1)
test = test.drop(['Utilities', 'Street', 'PoolQC',], axis=1)

"""
# 参考にならないデータを除外
outliers = [30, 88, 462, 631, 1322]
train = train.drop(train.index[outliers])
"""


# %%

def addTotalGrSF(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(row['1stFlrSF'] + row['2ndFlrSF'])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['TotalGrSF'] = dv


addTotalGrSF(train)
addTotalGrSF(test)

# 2020/03/28　追加


def addSoldYM(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(str(row['YrSold']) + '{:0>2}'.format(row['MoSold']))

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(int)
    # DataFrameと結合
    df['SoldYM'] = dv


addSoldYM(train)
addSoldYM(test)


def calcMean_LotArea(df, target, dv_count):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(dv_count[row[target]])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df[target + '_LotArea_Mean'] = dv


def addMean_LotArea(df1, df2, target):

    dv_count = df1.append(df2, ignore_index=True)

    # target毎のNLotAreaの平均を算出
    dv_count = dv_count.groupby(target)['LotArea'].mean()

    calcMean_LotArea(df1, target, dv_count)
    calcMean_LotArea(df2, target, dv_count)


addMean_LotArea(train, test, 'Neighborhood')
addMean_LotArea(train, test, 'Condition1')
addMean_LotArea(train, test, 'HouseStyle')
addMean_LotArea(train, test, 'MSSubClass')


def calcStd_LotArea(df, target, dv_count):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(dv_count[row[target]])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df[target + '_LotArea_Std'] = dv


def addStd_LotArea(df1, df2, target):

    dv_count = df1.append(df2, ignore_index=True)

    # target毎のNLotAreaの標準偏差を算出
    dv_count = dv_count.groupby(target)['LotArea'].std()

    calcStd_LotArea(df1, target, dv_count)
    calcStd_LotArea(df2, target, dv_count)


addStd_LotArea(train, test, 'Neighborhood')
addStd_LotArea(train, test, 'Condition1')
addStd_LotArea(train, test, 'HouseStyle')
# addStd_LotArea(train, test, 'MSSubClass')


def calcVar_LotArea(df, target, dv_count):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(dv_count[row[target]])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df[target + '_LotArea_Var'] = dv


def addVar_LotArea(df1, df2, target):

    dv_count = df1.append(df2, ignore_index=True)

    # target毎のNLotAreaの分散を算出
    dv_count = dv_count.groupby(target)['LotArea'].var()

    calcVar_LotArea(df1, target, dv_count)
    calcVar_LotArea(df2, target, dv_count)


addVar_LotArea(train, test, 'Neighborhood')
addVar_LotArea(train, test, 'Condition1')
addVar_LotArea(train, test, 'HouseStyle')
# addVar_LotArea(train, test, 'MSSubClass')

# %%
def addTotalSF(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(row['1stFlrSF']
                      + row['2ndFlrSF']
                      + row['TotalBsmtSF'])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['TotalSF'] = dv


addTotalSF(train)
addTotalSF(test)


def addYrBltAndRemod(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(row['YearBuilt']
                      + row['YearRemodAdd'])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['YrBltAndRemod'] = dv


addYrBltAndRemod(train)
addYrBltAndRemod(test)


def addTotal_sqr_footage(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(row['BsmtFinSF1']
                      + row['BsmtFinSF2']
                      + row['1stFlrSF']
                      + row['2ndFlrSF'])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['Total_sqr_footage'] = dv


addTotal_sqr_footage(train)
addTotal_sqr_footage(test)


def addTotal_Bathrooms(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(row['FullBath']
                      + (0.5 * row['HalfBath'])
                      + row['BsmtFullBath']
                      + (0.5 * row['BsmtHalfBath']))

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['Total_Bathrooms'] = dv


addTotal_Bathrooms(train)
addTotal_Bathrooms(test)


def addTotal_porch_sf(df):

    dv_ary = []
    for index, row in df.iterrows():

        dv_ary.append(row['OpenPorchSF']
                      + row['3SsnPorch']
                      + row['EnclosedPorch']
                      + row['ScreenPorch']
                      + row['WoodDeckSF'])

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['Total_porch_sf'] = dv


addTotal_sqr_footage(train)
addTotal_sqr_footage(test)


def addhastarget(df, target):

    dv_ary = []
    for index, row in df.iterrows():

        if np.isnan(row[target]) or row[target] == 0:
            dv_ary.append(0)
        else:
            dv_ary.append(1)

    # Seriesに変換
    dv = pd.Series(dv_ary).astype(float)
    # DataFrameと結合
    df['has' + target] = dv


addhastarget(train, 'PoolArea')
addhastarget(test, 'PoolArea')

addhastarget(train, '2ndFlrSF')
addhastarget(test, '2ndFlrSF')

addhastarget(train, 'GarageArea')
addhastarget(test, 'GarageArea')

addhastarget(train, 'TotalBsmtSF')
addhastarget(test, 'TotalBsmtSF')

addhastarget(train, 'Fireplaces')
addhastarget(test, 'Fireplaces')


# %%

def setAstype(train, test, colName, setType):

    train[colName] = train[colName].astype(setType)
    test[colName] = test[colName].astype(setType)


dec = {
    'LotShape': {
        'Reg': 4,
        'IR1': 3,
        'IR2': 2,
        'IR3': 1
    },
    'BsmtCond': {
        'Ex': 16,
        'Gd': 8,
        'TA': 4,
        'Fa': 2,
        'Po': 1,
        'NA': 0,
        'None': -9999
    },
    'BsmtQual': {
        'Ex': 16,
        'Gd': 8,
        'TA': 4,
        'Fa': 2,
        'Po': 1,
        'NA': 0,
        'None': -9999
    },
    'FireplaceQu': {
        'Ex': 16,
        'Gd': 8,
        'TA': 4,
        'Fa': 2,
        'Po': 1,
        'NA': 0,
        'None': -9999
    },
    'KitchenQual': {
        'Ex': 16,
        'Gd': 8,
        'TA': 4,
        'Fa': 2,
        'Po': 1,
        'NA': 0,
        'None': -9999
    },
    'PoolQC': {
        'Ex': 16,
        'Gd': 8,
        'TA': 4,
        'Fa': 2,
        'Po': 1,
        'NA': 0,
        'None': -9999
    },
    'GarageQual': {
        'Ex': 16,
        'Gd': 8,
        'TA': 4,
        'Fa': 2,
        'Po': 1,
        'NA': 0,
        'None': -9999
    },
    'MasVnrType': {
        'BrkCmn': 8,
        'BrkFace': 4,
        'CBlock': 2,
        'Stone': 1,
        'None': -9999
    },
}

train.replace(dec, inplace=True)
test.replace(dec, inplace=True)

# 型を設定（後の計算でのエラー回避のため）
setAstype(train, test, 'LotShape', 'float')
setAstype(train, test, 'BsmtCond', 'float')
setAstype(train, test, 'BsmtQual', 'float')
setAstype(train, test, 'FireplaceQu', 'float')
setAstype(train, test, 'KitchenQual', 'float')
# setAstype(train, test, 'PoolQC', 'float')
setAstype(train, test, 'GarageQual', 'float')
setAstype(train, test, 'MasVnrType', 'float')



# %%
""" 2020/06/06 全体の平均から差を求めてもスコアが悪化したためコメントアウト

# 2020/05/30 全体の平均値からの差を求める Start


def addMeanDiff(df1, df2, target):

    dv_ary1 = []
    dv_ary2 = []

    mean = df1[target].mean()

    for index, row in df1.iterrows():

        dv_ary1.append(row[target] - mean)

    for index, row in df2.iterrows():

        dv_ary2.append(row[target] - mean)

    # Seriesに変換
    dv1 = pd.Series(dv_ary1).astype(float)
    dv2 = pd.Series(dv_ary2).astype(float)

    # DataFrameと結合
    df1[target + '_MeanDiff'] = dv1
    df2[target + '_MeanDiff'] = dv2


for target_num in targets_num:
    addMeanDiff(train, test, target_num)

# 2020/05/30 全体の平均値からの差を求める End
"""

# %%
printTime('組み合わせ特徴量の作成開始')


def calcFeatureValue(df, targets_pair):

    ary_multi = []
    ary_div1 = []
    ary_div2 = []

    target1 = targets_pair[0]
    target2 = targets_pair[1]

    for index, row in df.iterrows():

        if np.isnan(row[target1]) or np.isnan(row[target2]) \
                or row[target1] == 0 or row[target2] == 0 \
                or row[target1] == -9999 or row[target2] == -9999:
            ary_multi.append(np.log(0.00001))
        else:
            ary_multi.append(np.log(row[target1] * row[target2]))

            """
        if np.isnan(row[target2]) or row[target2] == 0:
            ary_div1.append(0)
        else:
            ary_div1.append(row[target1] / row[target2])

        if np.isnan(row[target1]) or row[target1] == 0:
            ary_div2.append(0)
        else:
            ary_div2.append(row[target2] / row[target1])
            """

    # Seriesに変換
    dv_multi = pd.Series(ary_multi).astype(float)
    """
    dv_div1 = pd.Series(ary_div1).astype(float)
    dv_div2 = pd.Series(ary_div2).astype(float)
    """

    # DataFrameと結合
    df[target1 + '_multi_' + target2] = dv_multi
    """
    df[target1 + '_div_' + target2] = dv_div1
    df[target2 + '_div_' + target1] = dv_div2
    """


# 2変数の組み合わせのlistを取得
targets_pairs = list(itr.combinations(targets_num, 2))

# プログレスバーを表示する
with tqdm(total=len(targets_pairs)) as pbar:
    for targets_pair in targets_pairs:
        calcFeatureValue(train, targets_pair)
        calcFeatureValue(test, targets_pair)
        pbar.update(1)  # プログレスバーをアップデート

printTime('組み合わせ特徴量の作成終了')

# %%
# 2020/05/30 Target encodingをする Start

# ラベルエンコーディング用に学習データとテストデータをunion
lavel_x = train.append(test, ignore_index=True)

# カテゴリ変数をlabel encodingする
for c in targets_category:
    # 学習データとテストデータに基づいてラベルを設定
    le = LabelEncoder()
    le.fit(lavel_x[c])
    train[c] = le.transform(train[c])
    test[c] = le.transform(test[c])

# 2020/05/30 Target encodingをする End

# %% [markdown]
# ### 編集した学習データ、テストデータをデータベースに格納する

# %%
# データベースに学習データ、テストデータを格納（テーブル自体を上書き）
train.to_sql('train_featured', engine, index=False, if_exists='replace')
test.to_sql('test_featured', engine, index=False, if_exists='replace')

# %% [markdown]
# ### データベースから編集済の学習データ、テストデータを取得し、特徴量と目的変数に分ける

# %%
# データベースから学習データ、テストデータを取得
train_featured = pd.read_sql("SELECT * FROM train_featured", con=engine)
test_featured = pd.read_sql("SELECT * FROM test_featured", con=engine)

# 学習データを特徴量と目的変数に分ける
train_x = train_featured.drop(['Id', 'SalePrice'], axis=1)
train_y = train_featured['SalePrice']

# テストデータは特徴量のみなので、そのままでよい
test_x = test_featured.drop(['Id'], axis=1)
test_id = test_featured['Id']

train.shape

missing_percentage(test)


# %% [markdown]
# #### モデル作成とバリデーション
# LightGBMを使用してモデルを作成します。

# %%
# 2020/05/30 予想値と真の値の差が大きいデータを分析する Start
def func_write_prediction_result2csv(va_x, va_y, va_pred, loop_count):
    """
    予測値と真の値の差分を計算してcsvに出力する関数
    引き算の結果にはマイナスも出てくるので、マイナスを含めた場合、絶対値に変換した場合の2通りのcsvを出力する
    バリデーションは現在4回行われており、何回目のものか区別するためにloop_countを使用
    csvは、/kaggle/output/以下に作成される。
    prediction_result_model ... マイナスを含む
    prediction_result_abs_model ... 絶対値に変換
    """

    # 予測値をSeriesに変換
    se_va_pred = pd.Series(va_pred, va_y.index.values)
    se_va_pred.name = "prediction_"+va_y.name
    # print(type(se_va_pred))
    # print(se_va_pred)

    # 真の値と予測値の差分を計算（マイナスを含む）
    se_diff_y_pred = va_y - se_va_pred
    se_diff_y_pred.name = "diff_"+va_y.name
    # print(se_diff_y_pred)

    # 真の値と予測値の差分を計算（絶対値に変換）
    se_diff_y_pred_abs = se_diff_y_pred.abs()
    se_diff_y_pred_abs.name = "diff_abs_"+va_y.name
    # print(se_diff_y_pred_abs)

    # x, y を結合
    df_x_y = pd.concat([va_x, va_y], axis=1)
    # print(df_x_y)

    # x, y にpredを結合
    df_x_y_pred = pd.concat([df_x_y, se_va_pred], axis=1)
    # print(df_x_y_pred)

    # x, y, pred にマイナスを含む差分を結合
    df_pred_result = pd.concat([df_x_y_pred, se_diff_y_pred], axis=1)
    # print(df_pred_result)
    output_file_name = '/kaggle/output/prediction_result_model' + str(loop_count) + '.csv'
    df_pred_result.to_csv(output_file_name)

    # x, y, pred に絶対値に変換した差分を結合
    df_pred_result_abs = pd.concat([df_x_y_pred, se_diff_y_pred_abs], axis=1)
    # print(df_pred_result_abs)
    output_file_name = '/kaggle/output/prediction_result_abs_model' + str(loop_count) + '.csv'
    df_pred_result_abs.to_csv(output_file_name)
# 2020/05/30 予想値と真の値の差が大きいデータを分析する End


printTime('モデルの作成開始')

va_pred_list = []
va_weight_list = []
pred_list = []

# 学習データを学習データとバリデーションデータに分ける
kf = KFold(n_splits=24, shuffle=True, random_state=42)

loop_count = 0
for tr_idx, va_idx in kf.split(train_x):
    loop_count = loop_count+1
    tr_x, va_x = train_x.iloc[tr_idx], train_x.iloc[va_idx]
    tr_y, va_y = train_y.iloc[tr_idx], train_y.iloc[va_idx]

    # 2020/05/30 Target encodingをする Start

    # 2020/05/30 Target encodingをする End

    # 特徴量と目的変数をlightgbmのデータ構造に変換する
    lgb_train = lgb.Dataset(tr_x, tr_y)
    lgb_eval = lgb.Dataset(va_x, va_y)

    # ハイパーパラメータの設定
    """
    params = {
        'boosting_type': 'gbdt',
        'objective': 'regression_l2',
        'metric': 'l2',
        'num_leaves': 40,
        'learning_rate': 0.05,
        'feature_fraction': 0.9,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'lambda_l2': 2,
    }
    """

    params = {
        'objective': 'regression',
        'num_leaves': 4,
        'learning_rate': 0.01,
        'n_estimators': 5000,
        'max_bin': 200,
        'bagging_fraction': 0.75,
        'bagging_freq': 5,
        'bagging_seed': 7,
        'feature_fraction': 0.2,
        'feature_fraction_seed': 7,
        'verbose': -1,
    }

    # 学習の実行
    # カテゴリ変数をパラメータで指定している
    # バリデーションデータもモデルに渡し、学習の進行とともにスコアがどう変わるかモニタリングする
    model = lgb.train(params,
                      lgb_train,
                      num_boost_round=100,  # 作成する決定木の数を指定
                      # categorical_feature=targets_category,
                      valid_names=['train', 'valid'],
                      valid_sets=[lgb_train, lgb_eval],
                      verbose_eval=0)

    # バリデーションデータでのスコアの確認
    va_pred_lgb = model.predict(va_x)
    va_pred_list.append(va_pred_lgb)

    # バリデーションデータでのスコア(真の値の対数と予測値の対数の二乗平均平方根誤差 (RMSE))を計算する
    rmse_lgb = np.sqrt(mean_squared_error(np.log(va_y), np.log(va_pred_lgb)))

    # 予測
    pred_list.append(model.predict(test_x))

    # 2020/05/30 予想値と真の値の差が大きいデータを分析する Start
    func_write_prediction_result2csv(va_x, va_y, va_pred_lgb, loop_count)
    # 2020/05/30 予想値と真の値の差が大きいデータを分析する End

    # XGBoostモデルでの解析
    xgbtrain = xgb.DMatrix(tr_x, label=tr_y)
    xgbvaild = xgb.DMatrix(va_x, label=va_y)
    xgbtest = xgb.DMatrix(test_x)

    """
    params_xgb = {
        'learning_rate': 0.3,
        'n_estimators': 3460,
        'max_depth': 3,
        'min_child_weight': 0,
        'gamma': 0,
        'subsample': 0.7,
        'colsample_bytree': 0.7,
        'objective': 'reg:linear',
        'nthread': -1,
        'scale_pos_weight': 1,
        'seed': 27,
        'ret_alpha': 0.00006,
        'random_state': 71
    }
    """

    params_xgb = {
        'learning_rate': 0.12,
        'objective': 'reg:linear',
        'silent': 1,
        'random_state': 71
    }

    model_xgb = xgb.train(params_xgb,
                          xgbtrain,
                          170,
                          evals=[(xgbtrain, 'train'), (xgbvaild, 'eval')],
                          verbose_eval=0
                          )

    # バリデーションデータでのスコアの確認
    va_pred_xgb = model_xgb.predict(xgb.DMatrix(va_x))
    va_pred_list.append(va_pred_xgb)

    # バリデーションデータでのスコア(真の値の対数と予測値の対数の二乗平均平方根誤差 (RMSE))を計算する
    rmse_xgb = np.sqrt(mean_squared_error(np.log(va_y), np.log(va_pred_xgb)))

    # 予測
    pred_list.append(model_xgb.predict(xgbtest))

    """
    # RandomForestモデルでの解析
    model_rdm = RandomForestRegressor(n_estimators=500, n_jobs=-1, max_depth=15)
    model_rdm.fit(tr_x, tr_y)
    
    # バリデーションデータでのスコア確認
    va_pred_rdm = model_rdm.predict(va_x)
    va_pred_list.append(va_pred_rdm)
    
    # バリデーションデータでのスコア(真の値の対数と予測値の対数の二乗平均平方根誤差 (RMSE))を計算する
    rmse_rdm = np.sqrt(mean_squared_error(np.log(va_y), np.log(va_pred_rdm)))

    # 予測
    pred_list.append(model_rdm.predict(test_x))
    """

    # 加重平均を求めるための重さを設定
    if rmse_lgb > rmse_xgb:
        va_weight_list.append(0)
        if rmse_xgb > 0.15:
            va_weight_list.append(0)
        else:
            va_weight_list.append(1)
    else:
        if rmse_lgb > 0.15:
            va_weight_list.append(0)
        else:
            va_weight_list.append(1)
        va_weight_list.append(0)

    print(f'RMSE:LightGBM {rmse_lgb:.4f} ,XGBoost {rmse_xgb:.4f}')

    """
    if rmse_lgb > rmse_xgb:
        if rmse_lgb > rmse_rdm:
            va_weight_list.append(0)
            va_weight_list.append(1)
            va_weight_list.append(1)
        else:
            va_weight_list.append(1)
            va_weight_list.append(1)
            va_weight_list.append(0)
    else:
        if rmse_xgb > rmse_rdm:
            va_weight_list.append(1)
            va_weight_list.append(0)
            va_weight_list.append(1)
        else:
            va_weight_list.append(1)
            va_weight_list.append(1)
            va_weight_list.append(0)

    print(f'RMSE:LightGBM {rmse_lgb:.4f} ,XGBoost {rmse_xgb:.4f} ,RandomForest {rmse_rdm:.4f}')
    """

    """
    # 結果の可視化
    sns.jointplot(
        va_y,
        va_pred_lgb,
        kind="reg",
        xlim=(0, 600000),
        ylim=(0, 600000)
    ).set_axis_labels("true", "pred(LightGBM)")

    sns.jointplot(
        va_y,
        va_pred_xgb,
        kind="reg",
        xlim=(0, 600000),
        ylim=(0, 600000),
        color="g"
    ).set_axis_labels("true", "pred(XGBoost)")
    """

va_pred_list = np.array(va_pred_list)
pred_list = np.array(pred_list)

print(va_weight_list)

# 提出用ファイルの作成
submission = pd.DataFrame({'Id': test_id, 'SalePrice': np.average(pred_list, axis=0, weights=va_weight_list)})
submission.to_csv('/kaggle/output/submission_ensemble.csv', index=False)

printTime('モデルの作成終了')

# %% [markdown]
# #### データの分析にどの特徴量が重要だったのかをプロット

# %%
lgb.plot_importance(model, figsize=(10, 30), max_num_features=100)

# %%
_, ax = plt.pyplot.subplots(figsize=(10, 30))
xgb.plot_importance(model_xgb, ax=ax, max_num_features=100)
