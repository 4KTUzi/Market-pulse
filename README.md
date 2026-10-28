# Market Pulse

A small dashboard showing an economic calendar (today and the next 7 days),
US stock indices, a stock watchlist, crypto prices, the crypto Fear & Greed
index, and market news headlines. A script refreshes the data every 30 minutes
and the page shows the latest numbers.

No API keys, no paid services, no packages to install (Python 3 only).

## Files

| File | What it does |
|---|---|
| `fetch_data.py` | Pulls prices and headlines, writes `data.json` and `data.js` |
| `index.html` | The dashboard. Reads `data.js`. |
| `test_parsers.py` | Offline checks of the parsing code (`python3 test_parsers.py`) |
| `.github/workflows/update.yml` | Runs the fetch every 30 minutes and publishes the site, free |

## 1. Try it on your computer

```
python3 fetch_data.py        # pulls live data (needs internet)
```

Then double-click `index.html`. To preview the layout without internet,
run `python3 fetch_data.py --demo` instead (synthetic numbers, clearly
labelled on the page).

## 2. Put it online and keep it refreshed (free)

1. Create a **public** repository on GitHub and upload all these files,
   keeping the `.github/workflows/update.yml` path exactly as it is.
   (Free GitHub Pages needs a public repo. Nothing private is in here.)
2. In the repo go to **Settings > Pages** and set **Source** to **GitHub Actions**.
3. Go to the **Actions** tab, open **Update market data**, click **Run workflow**.
4. When it finishes, the site address appears in the run summary.

After that it updates itself every 30 minutes (at :07 and :37 past each hour).
To change how often, edit the `cron` line in the workflow (times there are in UTC).
Each update saves a small commit to the repo, so expect about 48 a day.

**Live crypto prices:** while the page is open, the crypto prices and 24h
change tick in real time from Binance's public price feed (no key needed).
A small badge next to "Crypto" shows "Live" when connected. If the feed can't
connect (for example it is blocked on your network or in your country), the
badge says so and the table keeps the last 30-minute update. Everything else
(stocks, news, calendar) refreshes on the 30-minute schedule.

Good to know:
- GitHub can start scheduled runs a few minutes late. The page warns you if the data looks overdue.
- GitHub may pause scheduled runs on a repo with no activity for 60 days. If that happens, re-enable it from the Actions tab.

## 3. Change what it tracks

Open `fetch_data.py` and edit the lists at the top: `INDICES`, `MACRO`,
`WATCHLIST`, `CRYPTO_IDS` (CoinGecko ids) and `FEEDS` (news RSS links).
For the calendar, `CALENDAR_COUNTRIES` and `CALENDAR_IMPACTS` choose which
countries and importance levels appear.

## Economic calendar

- Events (CPI, jobs report, central bank decisions and so on) come from a free
  weekly feed, with forecast and previous values where available. By default it
  shows USD, EUR, GBP, JPY and CNY events rated High or Medium impact.
- Fed rate decisions are also added from a built-in list of the 2026 FOMC
  dates (decisions at 2:00 pm New York time), so they show up even if the feed
  is down. Add next year's dates to `FOMC_DECISION_DATES` each year.
- Times are shown in the viewer's own time zone. Earlier events today are dimmed.
- The feed gives scheduled times, forecasts and previous values, but not the
  released result.

## Known limits

- **Not tested live yet.** The environment this was built in blocked the data
  sites, so the live fetch has not been run. The parsing is checked with
  sample responses only. Run it once yourself (step 1) and check the output.
- **Stock prices use Yahoo Finance's public chart address, which is unofficial.**
  It can rate-limit or block cloud servers such as GitHub's. If stock rows
  are missing after a run, the fix is to switch `fetch_quote()` to a keyed
  source such as Finnhub or Alpha Vantage (free tiers exist).
- **The calendar feed is also unofficial and untested live.** It is a free
  community-used address, so it could change format or stop working. If it
  fails, the page still shows the Fed dates and says some sources were
  unavailable. Swapping to another calendar source only means editing
  `fetch_calendar()` and `parse_calendar_item()`.
- CoinGecko's free tier is rate-limited, which is fine for 4 runs a day.
- News shows headline, source, link and time only. Tags and the "possible
  mover" flag come from keyword matching. They are a prompt to look closer,
  not a prediction.
- Prices may be delayed, and nothing here is financial advice.

## Ideas for later

- Add UAE / DFM stocks and gold in AED.
- Show released results on the calendar next to the forecast (needs a source that provides them).
- Send the summary to Telegram or email each run.
- On a paid Claude plan, a scheduled task could write a short "why this matters" briefing from this data.
