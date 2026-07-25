# Meesho Support Ticket Automation

A Python + Selenium based automation tool that automatically raises Meesho support tickets for return orders across multiple seller accounts.

## Features

- ✅ Multi-account processing
- ✅ Automatic login to Meesho Supplier Panel
- ✅ Reads pending folders automatically
- ✅ Searches returns using AWB number
- ✅ Extracts Sub Order ID
- ✅ Automatically fills support ticket form
- ✅ Uploads:
  - Reverse Waybill Image
  - Product Image
  - Unboxing Video
- ✅ Detects "Ticket Already Raised" errors
- ✅ Moves processed folders to appropriate directories
- ✅ Generates execution summary report
- ✅ Session recovery after interruption
- ✅ Graceful shutdown support

---

## Project Structure

```
project/
│
├── main.py
├── utils.py
├── details.json
│
├── Accounts/
│   ├── Account1/
│   │   ├── pending/
│   │   ├── done/
│   │   └── already_raised/
│   │
│   └── Account2/
│
├── Reports/
│
└── session/
```

---

## Requirements

- Python 3.10+
- Google Chrome
- ChromeDriver
- Selenium

Install dependencies:

```bash
pip install -r requirements.txt
```

or

```bash
pip install selenium webdriver-manager
```

---

## Configuration

Create a `details.json` file.

Example:

```json
[
    {
        "email": "example@email.com",
        "password": "password",
        "accountName": "Account1",
        "state": "intact/"
    }
]
```

---

## Folder Format

Each pending folder should contain:

```
Pending Folder
│
├── ReverseWaybill.jpg
├── ProductImage.jpg
├── UnboxingVideo.mp4
└── metadata
```

The folder name should contain the required AWB and Packet ID information expected by the automation.

---

## Workflow

1. Login to Meesho account.
2. Read next pending folder.
3. Search return using AWB.
4. Fetch Sub Order ID.
5. Open Support page.
6. Fill:
   - State
   - Sub Order Number
   - AWB Number
   - Packet ID
7. Upload all required files.
8. Fill issue description.
9. Submit ticket.
10. Move folder based on result:
    - `done`
    - `already_raised`
    - `pending` (if failed)

---

## Summary Report

After execution, the script generates a report containing:

- Total Processed
- Successful Tickets
- Failed Tickets
- Already Raised Tickets
- Skipped Tickets
- Success Rate
- Folder-wise status

Reports are saved inside:

```
Reports/
```

---

## Error Handling

The automation handles:

- Login failures
- Missing returns
- Missing Sub Order ID
- Upload failures
- Already raised ticket detection
- Unexpected Selenium exceptions
- Session recovery

---

## Technologies Used

- Python
- Selenium
- ChromeDriver
- JSON
- pathlib
- datetime

---

## Notes

- Keep Chrome updated.
- Do not modify the folder structure while the automation is running.
- Ensure stable internet connectivity.
- Verify Meesho account credentials before execution.

---

## Future Improvements

- Logging using Python logging module
- Email notifications
- Docker support
- Parallel account execution
- GUI dashboard
- Database integration

---

## Author

Developed for automating Meesho Supplier Panel support ticket creation using Selenium.
