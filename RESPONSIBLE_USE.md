# Responsible Use

NumberTrace helps you decide how to handle **a call you received**. It is not a people-search tool.

**Do**
- Check one number that contacted you.
- Treat every web result as an *unverified public reference*.
- Verify a claimed company by calling its official number yourself.
- Report scams to your operator and to the authorities (Sri Lanka: TRCSL, Sri Lanka CERT).

**Do not**
- Use it to find, track, stalk or harass anyone.
- Enumerate number ranges or run bulk lookups (the tool blocks this on purpose).
- Treat a social-media mention as proof of who owns an account.
- Call someone a scammer based on one complaint or a "risk" score.
- Add data from leaks, breaches, data brokers, or scraping that breaks a site's terms.

## Features we deliberately did not build
| Request | Why not | Safe alternative shipped |
|---|---|---|
| Find the owner's social accounts via contact-sync / password-reset probes | Account enumeration of private people, breaks platform terms | Social mentions only when they appear in normal indexed search results, labelled "ownership not established" |
| Name/address lookup | Exposes sensitive personal data | Business pages that publicly list the number |
| Live location | Not possible from a number; would be surveillance | Allocation region with portability warning |
| Scraping Google/Bing result pages | Violates terms, CAPTCHAs | Official APIs + manual search links |
| Bulk / range scanning | Mass surveillance | One number per action, input validation, rate limits |
