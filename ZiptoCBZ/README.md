# ZiptoCBZ

Rename `.zip` comic archives to `.cbz` and flatten redundant same-named folders
inside `.cbz` archives.

## Usage

```powershell
python .\zip_to_cbz.py "C:\path\to\comics"
```

To process only one archive:

```powershell
python .\zip_to_cbz.py "C:\path\to\comics\Example.zip"
```

To include subdirectories:

```powershell
python .\zip_to_cbz.py "C:\path\to\comics" --recursive
```

If `Example.zip` and `Example.cbz` both exist, the script compares their file
sizes and moves the smaller archive into a `Duplicates` folder. If both files
are the same size, it keeps the existing `.cbz` and moves the `.zip` into
`Duplicates`.

After conversion, the script also scans `.cbz` files. If an archive contains a
single top-level folder named exactly like the archive, for example
`Example.cbz` containing `Example/page001.jpg`, the contents are moved to the
archive root and the redundant folder is removed. Before replacing the original
archive with the flattened version, the script moves the original archive into
`Duplicates` as a backup.
