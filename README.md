### Whatsapp Messaging

Integrate Whatsapp messaging with frappe

Workflow diagram:

```mermaid
flowchart TD
    %% Frappe Host Layer
    subgraph "Frappe Host Layer"
        FrappeFramework["Frappe Framework"]:::frappe
    end

    %% Application Logic Layer
    subgraph "Application Logic Layer"
        WA["Whatsapp Messaging App"]:::app

        subgraph "Controller & Hooks"
            Controller["Controller"]:::controller
            Hooks["Hooks"]:::controller
        end

        subgraph "Async Tasks"
            Cron["Cron"]:::tasks
            DocEvents["Doc Events"]:::tasks
            Scheduler["Scheduler"]:::tasks
        end

        subgraph "Utilities & Config"
            Config["Config"]:::config
            subgraph "Utils"
                LogManager["LogManager"]:::config
                MediaController["MediaController"]:::config
                MessageController["MessageController"]:::config
            end
        end
    end

    %% Document/Data Model Layer
    subgraph "Document/Data Model Layer"
        DoctypeModules["Doctype Modules (Conversations,Messages,Media,etc.)"]:::doctype
    end

    %% Asset/Client-side Layer
    subgraph "Asset/Client-side Layer"
        subgraph "Client-side Assets"
            PublicAssets["Public Assets (JS Bundles)"]:::assets
            Templates["Templates"]:::assets
        end
    end

    %% Connections
    FrappeFramework -->|"installs"| WA
    WA -->|"routes_to"| Controller
    WA -->|"routes_to"| Hooks
    Controller -->|"triggers"| Cron
    Controller -->|"triggers"| DocEvents
    Controller -->|"triggers"| Scheduler
    Hooks -->|"triggers"| Cron
    Hooks -->|"triggers"| DocEvents
    Hooks -->|"triggers"| Scheduler
    Cron -->|"updates"| DoctypeModules
    DocEvents -->|"updates"| DoctypeModules
    Scheduler -->|"updates"| DoctypeModules
    Controller -->|"CRUD"| DoctypeModules
    WA -->|"configured_by"| Config
    Controller -->|"uses"| Config
    Controller -->|"uses"| LogManager
    Controller -->|"uses"| MediaController
    Controller -->|"uses"| MessageController
    Cron -->|"uses"| LogManager
    Cron -->|"uses"| MediaController
    Cron -->|"uses"| MessageController
    WA -->|"serves"| PublicAssets
    WA -->|"serves"| Templates
    FrappeFramework -->|"renders"| PublicAssets
    FrappeFramework -->|"renders"| Templates

    %% Click Events
    click WA "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/"
    click Controller "https://github.com/nani-samireddy/whatsapp_messaaging/blob/develop/whatsapp_messaging/controller.py"
    click Hooks "https://github.com/nani-samireddy/whatsapp_messaaging/blob/develop/whatsapp_messaging/hooks.py"
    click Cron "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/tasks/cron"
    click DocEvents "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/tasks/doc_events"
    click Scheduler "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/tasks/scheduler"
    click DoctypeModules "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/whatsapp_messaging/doctype/"
    click Config "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/config/"
    click LogManager "https://github.com/nani-samireddy/whatsapp_messaaging/blob/develop/whatsapp_messaging/utils/log_manager.py"
    click MediaController "https://github.com/nani-samireddy/whatsapp_messaaging/blob/develop/whatsapp_messaging/utils/media_controller.py"
    click MessageController "https://github.com/nani-samireddy/whatsapp_messaaging/blob/develop/whatsapp_messaging/utils/message_controller.py"
    click PublicAssets "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/public/"
    click Templates "https://github.com/nani-samireddy/whatsapp_messaaging/tree/develop/whatsapp_messaging/templates/"

    %% Styles
    classDef frappe fill:#ffcc00,stroke:#333,stroke-width:2px;
    classDef app fill:#88cc88,stroke:#333,stroke-width:2px;
    classDef controller fill:#66a3ff,stroke:#333,stroke-width:2px;
    classDef tasks fill:#ff9966,stroke:#333,stroke-width:2px;
    classDef doctype fill:#ccccff,stroke:#333,stroke-width:2px;
    classDef config fill:#cc99ff,stroke:#333,stroke-width:2px;
    classDef assets fill:#99ccff,stroke:#333,stroke-width:2px;
```

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app whatsapp_messaging
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/whatsapp_messaging
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
