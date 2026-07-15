# Local Paper Deletion Design

## Goal

Allow the user to remove an unwanted paper directly from the local Daily Paper interface. Deletion removes only the current library record. A later automatic search or manual addition may add the same paper again.

## User Experience

- Show a trash icon in the paper detail view only when the site is running on localhost.
- Clicking the icon opens a confirmation dialog containing the paper title.
- Confirming removes the paper, refreshes the sidebar and metrics, and selects the next available paper.
- While another paper operation is running, deletion returns a clear conflict message instead of modifying the store.
- The public static site remains read-only and does not show the delete control.

## Data Flow

1. The browser sends the selected paper identity to `POST /api/papers/delete`.
2. The local server acquires the existing paper-operation lock.
3. The paper service creates a timestamped backup of the current data files.
4. It removes records matching the paper's identity keys from the current store.
5. It writes the updated library to both `data/papers.json` and `docs/papers.json`.
6. The browser reloads `papers.json` and updates the current selection.

No tombstone or ignore list is created, so future discovery can re-add the paper.

## Validation And Errors

- Reject empty or invalid paper payloads.
- Return `404` when no matching record exists.
- Return `409` while an automatic search or another mutation is running.
- Do not expose a delete endpoint through GitHub Pages.
- Preserve the existing automatic backup behavior before any destructive library mutation.

## Testing

- Unit-test identity-based deletion and the not-found path.
- Verify both data outputs contain one fewer paper after deletion.
- Verify later `merge_papers` can add the deleted paper again.
- Browser-test confirmation, cancellation, successful refresh, and localhost-only visibility.
