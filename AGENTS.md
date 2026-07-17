# Repository maintenance instructions

## Project feature catalog

`docs/project_feature_catalog.md` is the canonical inventory of features that are currently implemented in this repository.

Any change that adds, removes, or materially changes a user-visible feature, page, workflow, API, role, permission, data scope, configuration, integration, script, or deployment capability must update that document in the same task. Update the affected section rather than only appending a changelog entry, then also update its audit date, API/page/role tables when applicable, explicit limitations, test baseline, and changelog.

The catalog must distinguish implemented, conditionally available, backend-only, and unimplemented behavior. Do not describe plans or database placeholders as completed product functionality. Never place account passwords or other secrets in the public catalog; keep local demo credentials only in the ignored `docs/demo_accounts_private.md` file.
