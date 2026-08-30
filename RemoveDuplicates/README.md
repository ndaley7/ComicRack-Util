# RemoveDuplicates

Find duplicate `.zip` and `.cbz` archives directly inside a ComicRack source
folder, verify matches with SHA-256, and move duplicate copies into
`_DUPLICATES`.

```powershell
python .\RemoveDuplicates\remove_duplicates.py "C:\path\to\comics"
```

The tool only hashes files that share the same byte size. When exact duplicate
hashes are found, it keeps a preferred copy and moves the others. A `.cbz` is
preferred over a `.zip`; otherwise the shortest, then alphabetically earliest,
filename is kept.

Moved files are logged to `_DUPLICATES\duplicates.log`.
