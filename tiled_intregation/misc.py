import pandas as pd

# XDI files are comment-header (#) followed by tab/space-delimited columns
# Read skipping the header lines
with open("/home/sairam/LightshowAI/LightshowAI/data/Anatase.nor.xdi") as f:
    lines = f.readlines()

# Find where data starts (after the header block ending with "---")
data_start = 0
column_names = []
for i, line in enumerate(lines):
    if line.startswith("#"):
        if line.startswith("# Column."):
            # e.g. "# Column.1: energy eV"
            col_name = line.split(":")[-1].strip()
            column_names.append(col_name)
        continue
    if line.strip() == "---" or line.strip().startswith("---"):
        data_start = i + 1
        continue
    if not line.startswith("#"):
        data_start = i
        break

df = pd.read_csv(
    "/home/sairam/LightshowAI/LightshowAI/data/Anatase.nor.xdi",
    comment="#",
    delim_whitespace=True,
    header=None,
    skiprows=data_start,
)
if column_names:
    df.columns = column_names[:len(df.columns)]

df.to_csv("/home/sairam/LightshowAI/LightshowAI/data/Anatase.nor.csv", index=False)