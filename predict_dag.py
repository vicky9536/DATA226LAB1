# -*- coding: utf-8 -*-
"""predict_dag.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1KdMEdZEmLpKtvU9cCpxX5GGIGn__Z_BK
"""

from airflow import DAG
from airflow.models import Variable
from airflow.decorators import task

from datetime import timedelta
from datetime import datetime
import snowflake.connector
import requests


def return_snowflake_conn():

    user_id = Variable.get('snowflake_userid')
    password = Variable.get('snowflake_password')
    account = Variable.get('snowflake_account')

    conn = snowflake.connector.connect(
        user=user_id,
        password=password,
        account=account, 
        warehouse='compute_wh',
        database='dev'
    )

    return conn.cursor()


@task
def train(cur, symbol, train_input_table, forecast_function_name_prefix):
    
    # Create train_view, customized forecast_function and model for each symbol 
    train_view = f"dev.adhoc.train_stock_view_{symbol}"
    forecast_function_name = f"{forecast_function_name_prefix}_{symbol}"

    create_view_sql = f"""CREATE OR REPLACE VIEW {train_view} AS
                          SELECT DATE, CLOSE, SYMBOL
                          FROM {train_input_table}
                          WHERE SYMBOL = '{symbol}';"""

    create_model_sql = f"""CREATE OR REPLACE SNOWFLAKE.ML.FORECAST {forecast_function_name} (
        INPUT_DATA => SYSTEM$REFERENCE('VIEW', '{train_view}'),
        SERIES_COLNAME => 'SYMBOL',
        TIMESTAMP_COLNAME => 'DATE',
        TARGET_COLNAME => 'CLOSE',
        CONFIG_OBJECT => {{ 'ON_ERROR': 'SKIP' }}
    );"""

    try:
        cur.execute(create_view_sql)
        cur.execute(create_model_sql)
        cur.execute(f"CALL {forecast_function_name}!SHOW_EVALUATION_METRICS();")
    except Exception as e:
        print(e)
        raise


@task
def predict(cur, symbol, train_view, train_input_table, forecast_table_prefix, final_table_prefix, forecast_function_name_prefix):
    """
     - Generate predictions and store the results to a table named forecast_table.
     - Union your predictions with your historical data, then create the final table
    """
    forecast_table = f"{forecast_table_prefix}_{symbol}"
    final_table = f"{final_table_prefix}_{symbol}"
    forecast_function_name = f"{forecast_function_name_prefix}_{symbol}"

    make_prediction_sql = f"""BEGIN
        -- This is the step that creates your predictions.
        CALL {forecast_function_name}!FORECAST(
            FORECASTING_PERIODS => 7,
            -- Here we set your prediction interval.
            CONFIG_OBJECT => {{'prediction_interval': 0.95}}
        );
        -- These steps store your predictions to a table.
        LET x := SQLID;
        CREATE OR REPLACE TABLE {forecast_table} AS SELECT * FROM TABLE(RESULT_SCAN(:x));
    END;"""

    create_final_table_sql = f"""CREATE OR REPLACE TABLE {final_table} AS
        SELECT '{symbol}' AS SYMBOL, DATE, CLOSE AS actual, NULL AS forecast, NULL AS lower_bound, NULL AS upper_bound
        FROM {train_input_table}
        WHERE SYMBOL = '{symbol}'

        UNION ALL

        SELECT '{symbol}' as SYMBOL, ts as DATE, NULL AS actual, forecast, lower_bound, upper_bound
        FROM {forecast_table};"""

    try:
        cur.execute(make_prediction_sql)
        cur.execute(create_final_table_sql)
    except Exception as e:
        print(e)
        raise


with DAG(
    dag_id = 'TrainPredict_test',
    start_date = datetime(2024,9,21),
    catchup=False,
    tags=['ML', 'ELT'],
    schedule = '30 2 * * *'
) as dag:

    train_input_table = "dev.raw_data.time_series_daily"
    forecast_table_prefix = "dev.adhoc.stock_price_forecast"
    final_table_prefix = "dev.analytics.forecast_stock_price"
    forecast_function_name_prefix = "dev.analytics.predict_stock_price"

    cur = return_snowflake_conn()
    symbols = ["IBM", "AAPL", "NVDA"]

    for symbol in symbols:
        print(f"Training and predicting for symbol: {symbol}")
        train_task = train(cur, symbol, train_input_table, forecast_function_name_prefix)
        predict_task = predict(cur, symbol, train_task, train_input_table, forecast_table_prefix, final_table_prefix, forecast_function_name_prefix)

        train_task >> predict_task
