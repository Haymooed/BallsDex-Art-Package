# BallsDex V3 Art Package 🎨

The **Art Package** for **BallsDex V3** allows players to submit and view custom artwork associated with specific balls or collectibles. The system is fully configurable via the **admin panel** and follows the **same structure and conventions** as the BallsDex V3 Merchant Package.

This package is designed to integrate cleanly with the BallsDex V3 custom package system.

---

## Installation (`extra.toml`)

Add the following entry to `config/extra.toml` so BallsDex installs the package automatically:

```toml
[[ballsdex.packages]]
location = "git+https://github.com/Caylies/Art-BD-Package.git"
path = "art"
enabled = true
editable = false
```

The package is distributed as a standard Python package — no manual file copying required.

---

## Admin Panel Integration

The art system works entirely through the admin panel, following the same format and patterns used by the BallsDex V3 Merchant Package.

No values are hardcoded. All settings and data are editable from the panel.

### Configuration

Configuration follows the BallsDex V3 custom package guidelines:
https://wiki.ballsdex.com/dev/custom-package/

#### Art Settings (singleton)
- Enable / disable art submissions and viewing
- Require approval toggle (if disabled, submissions are auto-approved)
- Maximum submissions per player per day

#### Art Entries
- Linked Ball
- Artist (player who submitted)
- Title (optional)
- Description (optional)
- Media URL (image, video, etc.)
- Status (Pending/Approved/Rejected)
- Enabled toggle
- Review information (reviewer, review date, rejection reason)

Admins can:
- View all art entries with filtering and search
- Approve or reject submissions
- Bulk approve/reject actions
- Manage visibility (enable/disable entries)

---

## Commands (Slash Commands / app_commands)

### Player Commands

- `/art submit <ball> <media_url> [title] [description]` — Submit artwork tied to a specific ball.
- `/art view <ball>` — View approved art entries for a given ball.
- `/art info <entry_id>` — View details of a specific art entry (title, description, media, artist).

### Admin Commands

- `/art review` — List pending artwork submissions.
- `/art approve <entry_id>` — Approve an art entry.
- `/art reject <entry_id> [reason]` — Reject an art entry with an optional reason.

---

## Behaviour Requirements

- Art submissions start in Pending state (unless auto-approval is enabled).
- Only Approved art is visible with `/art view`.
- Admin approvals/rejections update status and optionally notify submitters via DM.
- Validates media URLs on submission.
- Respects daily submission limits per player.
- Artists can view their own submissions regardless of status.

---

## Embed Output

Approved artwork embeds include:
- Title
- Artist (player) with avatar
- Ball name
- Description
- Media preview (image/video link)
- Submission date
- Entry ID

---

## Technical Notes

- Follows the same file structure, setup flow, and patterns as the Merchant Package.
- Uses async `setup(bot)` and modern `app_commands`.
- Fully compatible with BallsDex V3 models (Ball, Player, etc.).
- Designed to plug directly into the BallsDex V3 extra/custom package loader.
- Uses singleton pattern for settings management (similar to django-solo).

This package feels native to BallsDex V3, consistent with existing official and community packages, and easy for admins to manage through the panel.

---

## License

MIT License
