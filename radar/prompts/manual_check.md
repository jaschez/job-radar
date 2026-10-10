Weekly check, no questions asked, of target companies whose postings cannot be read through an API.

The candidate:

{PROFILE}

Search rules:

{RULES}

Role families searched: {FAMILIES}.

For each company below, open its careers page with WebFetch (and at most one web search if the page does not load) and look for postings compatible with the rules above.

{COMPANIES}

Write the file `{OUT_FILE}` with the Write tool: a JSON array with
`{"company", "title", "location", "url", "fit": "High|Medium|Low", "why": "<one sentence in {LANGUAGE}>"}` only for compatible postings (an empty array if there are none). Do not invent postings: if you cannot see a page, add `{"company": "...", "error": "reason"}`. Do nothing else.
