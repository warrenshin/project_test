import pandas as pd

file_path = r"C:\work\project_test\주식상황1.xlsx - 시트1.csv"

df = pd.read_csv(file_path, encoding="utf-8-sig")

import sys
sys.stdout.reconfigure(encoding="utf-8")

print(df.to_string(index=True))
print(f"\n행: {df.shape[0]}, 열: {df.shape[1]}")
print(f"\n컬럼 목록: {list(df.columns)}")
