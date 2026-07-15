# Web Direction Management Design

## Goal

Fix collisions between Chinese direction names and let a user add, edit, or
remove research directions directly in the web interface. In local mode, saved
directions become the project's persistent search configuration.

## Direction identity

- Keep an existing valid, unique ID when editing a direction.
- Generate new IDs as `topic-<stable-hash>` from the normalized direction name.
- During browser-storage migration, replace duplicate or legacy fallback IDs
  such as `direction` with stable hashed IDs.
- Resolve the unlikely case of equal hashes with a deterministic numeric suffix.

This keeps Chinese names distinct while avoiding Unicode IDs in command-line,
JSON, and automation paths.

## Web editor

Replace the free-form textarea with repeated direction rows. Each row contains
a direction-name input, a comma-separated keyword input, and an icon-only
delete button. An `Add direction` button appends an empty row. Save validates
that every row has a name and at least one keyword.

The existing Reset and Copy JSON actions remain. Reset restores the current
project configuration rather than deleting papers.

## Persistence

- Hosted/static mode continues to store custom directions in browser storage
  and sends them with manually triggered GitHub workflows.
- Local mode posts the normalized directions to `/api/topics/save`.
- The local service validates the payload, creates a timestamped backup, writes
  `config/topics.json`, and updates the top-level topic catalog in both paper
  stores without deleting or rewriting paper records.
- The browser also retains the normalized custom catalog so existing papers are
  immediately reclassified by the edited keywords.

## Failure handling

The server rejects empty names, empty keyword lists, duplicate IDs, excessive
field lengths, and attempts to save while another paper operation is running.
The dialog remains open and displays a concise error when persistence fails.

## Verification

- Unit tests cover normalization, stable IDs, persistence, backups, and the API
  route.
- Browser QA verifies migration of `可解释性` and `流形` into separate IDs,
  adding a new direction, deleting a row, saving, and responsive layout.
