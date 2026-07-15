# Three Paper Directions Design

## Goal

Show and search only three default directions: Vision Token Pruning, GRPO, and 可解释性.

## Design

`config/topics.json` remains the single source of truth. It will contain only the three requested directions and their search keywords. Existing paper records will be reindexed against this configuration so the current library immediately uses the new groups.

The frontend will bump its topic schema version. On the first reload after this change, it removes the old seven-direction browser override and loads the new server directions. Later user edits remain supported and are not reset again.

## Verification

- Confirm both paper JSON files contain exactly three topic definitions.
- Confirm the browser renders exactly three direction groups after reload.
- Confirm local run requests send exactly those three directions.
- Confirm the paper count is preserved during reindexing.
