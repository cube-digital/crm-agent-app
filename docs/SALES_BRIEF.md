# Sales brief — what this product is solving

Most of you have never sold anything for a living. That's fine. This 10-minute primer gives you enough context to make the agent useful rather than just clever.

## The world the user lives in

A **sales rep** works on a list of **deals**. Each deal is a single attempt to sell something (a piece of software, a service, a contract) to a single **buyer** (a prospective customer company). Inside the buyer there are one or more **contacts** — the actual humans the rep talks to.

A deal isn't a single moment. It's a multi-week or multi-month conversation:

> *"I emailed Maria last Tuesday with the proposal. She said her CFO wants to see ROI numbers before Friday. We're supposed to have a follow-up call this week, but she hasn't replied to my last two emails. We're in 'Contract Sent' stage. Forecast says $80k. I have 22 other deals like this."*

That conversation gets recorded as a stream of **activities** — emails sent and received, calls logged, meetings on the calendar, notes the rep typed in. Each deal has anywhere from a handful to a few hundred activities attached.

The **pipeline** is the company's ordered list of stages a deal moves through, e.g.:

```
Appointment Scheduled  →   v    →  Presentation Scheduled
        →  Decision Maker Bought-In  →  POC  →  Contract Sent  →  Closed Won
                                                              ↘  Closed Lost
```

## The two problems the agent solves

### 1. Reps can't read every email of every deal

A rep with 30 active deals and 200+ activities can't keep all the threads in their head. They forget who said what, when. They miss that "Maria stopped replying" or "the CFO got brought in last week — that's a green flag, push for a meeting." Important signals decay into the noise.

### 2. Reps act *reactively*, not *proactively*

Today the rep opens the CRM, looks at a list, and asks themselves *"who should I follow up with?"* — usually picking based on memory and gut. The really useful version is the opposite: **the system tells them**, *"Maria is in 'Contract Sent', it's been 9 days of silence, last activity was a positive call with the CFO, the next best action is a follow-up email with a redline of the contract. Here's a draft."*

That's what *proactive* means in this context. It isn't "agent runs on a cron." It's:

> **The agent watches the state of the world, notices when *something is worth doing*, and surfaces a concrete recommendation — without the user having to ask.**

## What makes a "next best action" good

A good recommendation has these properties:

1. **It's specific to *this* deal.** Not "follow up regularly." Something like: *"Send a follow-up to [maria@acme.com](mailto:maria@acme.com) referencing the Aug 14 pricing call; she requested CFO ROI numbers."*
2. **It cites evidence.** It points to the specific activities (email subjects, meeting timestamps) that justify the recommendation. The rep needs to trust it instantly.
3. **It's timely.** A recommendation that arrives a week too late is worse than nothing.
4. **It's *prioritised*.** Across 30 deals, the agent should say which one matters *right now* — biggest deal × strongest signal × shortest path to revenue.
5. **It says nothing when there's nothing to say.** Recommendation spam destroys trust.

## Vocabulary (use these terms)


| Term                     | Meaning                                                               |
| ------------------------ | --------------------------------------------------------------------- |
| Deal                     | The opportunity being sold. Has a stage, an amount, an owner.         |
| Buyer                    | The prospect company we're selling to.                                |
| Contact                  | A person inside the buyer.                                            |
| Champion                 | A contact actively pushing the deal internally.                       |
| Decision maker           | The person who signs the contract. Often *not* the champion.          |
| Pipeline                 | The ordered set of stages a deal can move through.                    |
| Stage                    | Where the deal sits in the pipeline right now.                        |
| Activity                 | An email, call, meeting, note, or task on the timeline.               |
| Stale                    | A deal where no activity has happened for "too long" given its stage. |
| Closed Won / Closed Lost | Terminal stages. The deal is over.                                    |
| Next best action (NBA)   | The single most valuable thing the rep should do next.                |


## Signals worth thinking about

When deciding the next best action, the kinds of signals a human rep would weigh:

- **Silence.** Days since last inbound from the buyer. Days since last outbound from the rep.
- **Stage age.** Deals stall — sitting in "POC" for 6 weeks is bad news.
- **Stakeholder coverage.** Have we talked to a decision maker yet, or only to a champion?
- **Sentiment / momentum.** Were the last few messages positive ("looking great, sending to legal") or negative ("we're re-evaluating budget")?
- **Concrete asks.** Did the buyer ask for *something specific* (pricing, security doc, redline) that we haven't delivered?
- **Calendar gaps.** A meeting was scheduled and then nothing followed up.
- **Deal size × stage probability.** A $500k deal in POC is more urgent than a $5k deal in the same stage.

Not all of these need to be in your first version. Pick the ones you can extract from the data and reason about confidently.

## Out of scope (don't get sucked in)

- Writing emails / generating outbound content. The output is a *recommendation*, not the artefact.
- Forecasting revenue.
- Multi-tenant security, auth, RBAC.
- Connecting to a real CRM (HubSpot, Salesforce). You have a sample DB.
- Pretty UIs. A CLI or a JSON endpoint is fine.

