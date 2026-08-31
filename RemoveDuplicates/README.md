# RemoveDuplicates

Find duplicate `.zip` and `.cbz` archives directly inside a ComicRack source
folder, verify matches with SHA-256, and move duplicate copies into
`_DUPLICATES`.

```powershell
python .\RemoveDuplicates\remove_duplicates.py "C:\path\to\comics"
```

The tool hashes files that share the same byte size. When exact duplicate
hashes are found, it keeps a preferred copy and moves the others. It also moves
obvious numbered download copies like `Example(1).zip` or `Example (2).cbz`
when the original `Example.zip` or `Example.cbz` is present. A `.cbz` is
preferred over a `.zip`; otherwise the shortest, then alphabetically earliest,
filename is kept.

Moved files are logged to `_DUPLICATES\duplicates.log`.
