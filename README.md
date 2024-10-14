# DATA226LAB1

- stock_dag file: running as an Airflow DAG which fetches the last 90 days stock price **for each company** (specified by different **symbols**), then combined the returned 90day_stock_price for three companies together. Then transform and load the data into Snowflake as a final table.

  
- predict_dag file: running as an Airflow DAG which contains train task and predict task. **For each company**, the train task creates a train_view and model. Then, utilizing the Snowflake ML forecast feature to predict the future 7-day stock price for each company and store the forecast values to separate tables. At last, combining the forecast values with the original data together as a final table **for each company**.
