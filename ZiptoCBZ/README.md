# ZiptoCBZ

Rename `.zip` comic archives to `.cbz`.

## Usage

```powershell
python .\zip_to_cbz.py "C:\path\to\comics"
```

To include subdirectories:

```powershell
python .\zip_to_cbz.py "C:\path\to\comics" --recursive
```

If `Example.zip` and `Example.cbz` both exist, the script compares their file
sizes and moves the smaller archive into a `Duplicates` folder. If both files
are the same size, it keeps the existing `.cbz` and moves the `.zip` into
`Duplicates`.
