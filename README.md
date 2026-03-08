# Lifegence CRM

Sales management (営業管理) for [Frappe](https://frappeframework.com/) / [ERPNext](https://erpnext.com/).

Provides deal pipeline management, lead scoring, activity tracking, and sales forecasting.

## Features

- Kanban pipeline board for deal management
- Lead scoring with configurable rules
- Activity timeline (calls, emails, meetings)
- Sales forecast with weighted pipeline
- ERPNext Quotation / Sales Order integration
- Campaign management

## Modules

### Sales CRM (営業管理)

| DocType | Description |
|---------|-------------|
| CRM Settings | Global CRM configuration |
| Deal | Deal (opportunity) management |
| Deal Stage | Pipeline stage definitions |
| Pipeline Board | Kanban board configuration |
| Lead Scoring Rule | Automated lead scoring rules |
| Activity | Activity records (calls/emails/visits) |
| Territory Target | Sales targets by territory |
| Sales Forecast | Revenue forecast entries |
| Campaign | Campaign management |
| Campaign Member | Campaign participants |
| Call Log | Phone call records |
| Meeting Note | Meeting notes and summaries |
| CRM Email Template | Email templates for CRM |
| CRM Notification Rule | Notification rules |

## Prerequisites

- Python 3.10+
- Frappe Framework v16+
- ERPNext v16+

## Installation

```bash
bench get-app https://github.com/lifegence/lifegence-crm.git
bench --site your-site install-app lifegence_crm
bench --site your-site migrate
```

## License

MIT - see [LICENSE](LICENSE)

## Contributing

Contributions are welcome. Please open an issue or pull request on [GitHub](https://github.com/lifegence/lifegence-crm).
