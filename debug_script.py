import pandas as pd
df = pd.read_excel('Crop_Recommendation_Dataset.xlsx')
with open('columns.txt', 'w') as f:
    f.write(str(df.columns.tolist()))
