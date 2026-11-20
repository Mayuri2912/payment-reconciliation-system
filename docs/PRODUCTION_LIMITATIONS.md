# What this solution would get wrong in production (exactly three sentences)

1. It matches only on an exact transaction ID with one bank line per transaction, so a real bank that pays in batches, nets off fees or uses its own references would make most records look "missing" or "unexpected".
2. It assumes one currency, weekends-only business days, a fixed T+2 window with one grace day and a bank file that always runs five days past month end, so holidays, midnight time-zone cut-offs and short bank files would label timing differences as missing or in-transit.
3. It detects duplicates only by a repeated transaction ID and was tested only on data it generated itself, so a real duplicate under a new ID, or two legitimate bank lines for one transaction, would be missed or wrongly flagged.
