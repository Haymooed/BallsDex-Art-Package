> [!IMPORTANT]
> Original code created by [Cayla](https://github.com/Caylies) you can view the orginal package here: [Art](https://github.com/Caylies/Art-BD-Package)

# BallsDex V3 Art Package 🎨

Art submission, review, and display package for **BallsDex V3**. Players can submit
artwork for balls, admins can review and moderate submissions, and everyone can
browse approved community art.

## Installation (`extra.toml`)

```toml
[[ballsdex.packages]]
location = "git+https://github.com/Haymooed/BallsDex-Art-Package.git"
path = "art"
enabled = true
editable = false
```

## Configuration (Admin Panel)

All settings are managed through the admin panel — nothing is hardcoded.

**Art Settings** (singleton):
- Enable / disable all art commands
- Toggle approval requirement (auto-approve or require review)
- Maximum submissions per player per day

**Art Entries**:
- Linked ball, artist, title, description, media URL
- Status: Pending / Approved / Rejected
- Enabled/disabled toggle
- Reviewer, review date, rejection reason
- Bulk approve/reject admin actions

## Slash Commands

### Player commands
| Command | Description |
|---------|-------------|
| `/art submit <ball> <attachment> [title] [description]` | Submit artwork for a ball |
| `/art view <ball>` | Browse approved artwork for a ball (paginated) |
| `/art info <entry_id>` | View details of a specific entry |
| `/art mine [status]` | View your own submissions, filtered by status |

### Admin commands
| Command | Description |
|---------|-------------|
| `/art review list [status]` | List submissions (filter by status) |
| `/art review approve <entry_id> ` | Approve an entry and notify the artist |
| `/art review reject <entry_id> [reason]` | Reject an entry and notify the artist |
| `/art spawn create <channel>` | Post all spawn/wild art into a forum channel |
| `/art card create <channel>` | Post all collection card art into a forum channel |

## Notes

- Follows V3 custom package conventions (`extra.toml`, Django app + discord.py cog).
- Paginated views using BallsDex's built-in `Pages` menu.
- Artist DM notifications on approval/rejection.
- Entry IDs displayed in hex for a clean look.
- Daily submission limit enforced per-player.

## License

MIT
