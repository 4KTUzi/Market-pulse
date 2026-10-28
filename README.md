# Market Pulse

A small dashboard showing US stock indices, a stock watchlist, crypto prices,
the crypto Fear & Greed index, and market news headlines. A script refreshes
the data every 6 hours and the page shows the latest numbers.

No API keys, no paid services, no packages to install (Python 3 only).

## Files

| File | What it does |
|---|---|
| `fetch_data.py` | Pulls prices and headlines, writes `data.json` and `data.js` |
| `index.html` | The dashboard. Reads `data.js`. |
| `test_parsers.py` | Offline checks of the parsing code (`python3 test_parsers.py`) |
| `.github/workflows/update.yml` | Runs the fetch every 6 hours and publishes the site, free |

## 1. Try it on your computer

```
python3 fetch_data.py        # pulls live data (needs internet)
```

Then double-click `index.html`. To preview the layout without internet,
run `python3 fetch_data.py --demo` instead (synthetic numbers, clearly
labelled on the page).

## 2. Put it online and refresh it every 6 hours (free)

1. Create a **public** repository on GitHub and upload all these files,
   keeping the `.github/workflows/update.yml` path exactly as it is.
   (Free GitHub Pages needs a public repo. Nothing private is in here.)
2. In the repo go to **Settings > Pages** and set **Source** to **GitHub Actions**.
3. Go to the **Actions** tab, open **Update market data**, click **Run workflow**.
4. When it finishes, the site address appears in the run summary.

After that it updates itself at 06:07, 12:07, 18:07 and 00:07 Dubai time.
To change the times, edit the `cron` line in the workflow (times there are in UTC).

Good to know:
- GitHub can start scheduled runs a few minutes late. The page warns you if the data looks overdue.
- GitHub may pause scheduled runs on a repo with no activity for 60 days. If that happens, re-enable it from the Actions tab.

## 3. Change what it tracks

Open `fetch_data.py` and edit the lists at the top: `INDICES`, `MACRO`,
`WATCHLIST`, `CRYPTO_IDS` (CoinGecko ids) and `FEEDS` (news RSS links).

## Known limits

- **Not tested live yet.** The environment this was built in blocked the data
  sites, so the live fetch has not been run. The parsing is checked with
  sample responses only. Run it once yourself (step 1) and check the output.
- **Stock prices use Yahoo Finance's public chart address, which is unofficial.**
  It can rate-limit or block cloud servers such as GitHub's. If stock rows
  are missing after a run, the fix is to switch `fetch_quote()` to a keyed
  source such as Finnhub or Alpha Vantage (free tiers exist).
- CoinGecko's free tier is rate-limited, which is fine for 4 runs a day.
- News shows headline, source, link and time only. Tags and the "possible
  mover" flag come from keyword matching. They are a prompt to look closer,
  not a prediction.
- Prices may be delayed, and nothing here is financial advice.

## Ideas for later

- Add UAE / DFM stocks and gold in AED.
- Add an economic calendar (Fed meetings, CPI, jobs reports).
- Send the summary to Telegram or email each run.
- On a paid Claude plan, a scheduled task could write a short "why this matters" briefing from this data.
