Mechanical task, no questions: synchronize the "Job Leads" tab of the Google Sheets spreadsheet `{SHEET_ID}` with the file `{OPS_FILE}`. Use only the Google Sheets connector tools.

Rules, without exception:
1. First read the whole "Job Leads" tab (columns A to Z). Every radar row carries its id in column Z (Notes) as `[radar:<id>]`.
2. **Append:** for each element of `append` whose `radar_id` does NOT appear in column Z yet, add a row at the end with `values`. In column A put the next free Job ID in the format `JL-0001`, `JL-0002`... Never insert rows in the middle or reorder.
3. **Close:** for each id in `close` present in the sheet: if column J (Status) is "Open", "Shortlisted" or "Not pursuing", change it to "Closed". Otherwise (Applied, Interviewing, Offer) do NOT touch it; append " · posting withdrawn {DATE}" to column Z.
4. **Update:** for each element of `update`, find its row by `[radar:<id>]` in column Z. If column J (Status) is "Open" or "Not pursuing", overwrite ONLY the given columns (H, I, O, P, Q, R, S). Otherwise touch nothing: the candidate is already moving that posting.
5. Do not modify any other cell. Columns J–L and T–Z belong to the candidate and are never overwritten (except the change to "Closed" in rule 3).
6. Never delete rows.
7. When done, write the file `{DONE_FILE}` with `{"appended": N, "updated": N, "closed": N, "kept_manual": N}` using the Write tool, and reply only with that JSON.
