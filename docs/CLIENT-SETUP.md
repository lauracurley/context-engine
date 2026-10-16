# Client setup and handoff

This guide is for the person preparing the local client pilot. Employees follow the [VS Code quickstart](../README.md#start-in-vs-code); they do not need to build the engine or run its Python commands.

## Prepare once

1. Supply the reviewed VSIX and record its hash. Developers build it using the [development guide](DEVELOPMENT.md); employees install the supplied file using **Extensions: Install from VSIX**. Use the 0.6.0 alpha candidate and retain its exact artifact hash with the handoff; version numbers alone do not identify a locally rebuilt package.
2. Provision the approved Python runtime and Git. The restricted macOS Apple Silicon profile uses Python 3.13.15 with `requirements-release-macos-arm64.txt`, including the approved Kotlin parser dependencies. Follow the pinned artifact and policy steps in the [client-test runbook](security/CLIENT-TEST-READINESS.md). Do not substitute the general optional semantic or structure dependency sets into this profile.
3. Supply the absolute Python executable path and, for a managed pilot, approved `contextEngine.storageRoot` and `contextEngine.policyPath` machine settings. Restart after storage changes; this does not migrate previous state. Runtime preparation is outside the extension: Get Started checks it and provides settings/help, but does not install packages.
4. Make the authorized repository checkouts available through the company's existing tools. Supply a manifest if the team needs advanced configuration; otherwise employees can create a Team or Personal scope from explicitly selected VS Code folders. Configure any optional local reviewer policy separately for knowledge workflows.
5. Run **Client-test readiness** and **Run synthetic benchmark** from the Command Palette or advanced sidebar. Check Kotlin parsing as well as text retrieval. These checks do not certify client account, MDM or release approval.

## Employee handoff

Provide the VSIX, interpreter path, any managed settings, the repository folders to select, and an approved agent/account choice. Ask the employee to use **Get started**, refresh code, and open the generated IDE workspace. The Codex IDE route uses the installed Codex extension; Context Engine's legacy CLI sign-in commands are not needed.

The generated workspace may prompt for workspace trust and permission to run its watch task. The employee can start that task manually through VS Code if automatic tasks are not enabled. Have them verify one cited lookup, then edit/save an authorized fixture and verify refreshed evidence. Workbench search remains available without an agent.

After changing the interpreter or upgrading the extension, use Open Codex IDE workspace again. Generated launch files capture their runtime/backend paths; unchanged workspaces are reused, and edited generated files are preserved in the previous copy. Start the conversation in its Context Engine folder. Retain the approved prior package and follow the runbook for rollback; do not assume old and new state are interchangeable.

Use the [alpha acceptance checklist](ALPHA-ACCEPTANCE.md) for the first test session, including knowledge review, managed handoff, schedule continuity and recovery.

## Feedback and limits

Optional local usage collection is off until explicitly enabled. **Usage report (review before sharing)** previews and saves only the validated report bytes, with no upload. The client reviews the saved file before sending it manually. Index status, diagnostic output, wiki pages and local inventories can contain company information; they are not vendor feedback reports.

This increment does not add a runtime installer, automatic updates, Git synchronization, shared approvals, additional telemetry or a cloud service. The vendor boundary remains the [standing contract](security/VENDOR-DATA-BOUNDARY.md). Client testing and approval remain separate from the automated developer checks.
