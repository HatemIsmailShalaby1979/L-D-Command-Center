# Storage

The storage engine provides local data persistence for the entire system. It manages on-disk storage of learning journeys, user preferences, exported content, and cached model outputs, and handles synchronization of SOPs to Notion when the user opts in. If this engine is deleted, all user data — journeys, exports, preferences, and external syncs — is lost, though the app's generative capabilities remain otherwise intact.
