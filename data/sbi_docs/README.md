# Manual import folder for public SBI documents

If `python -m rag.ingest` cannot fetch an official page (site blocks automated access,
no internet, robots.txt), save the public document here by hand:

1. Open the official SBI URL in your browser. Use "Save as PDF" / "Save page as" (HTML) or copy the text into a `.txt` file.
2. Put the file in this folder (`.pdf`, `.html` or `.txt`).
3. Optional but recommended: create `sources.json` here so citations show the real URL and title
   (see `sources.example.json`). Without it, the citation shows `manual-import:<filename>`; nothing is invented.
4. Run: `python -m rag.ingest --rebuild --skip-fetch`

Only import documents that SBI makes publicly available on official sbi.co.in pages.
