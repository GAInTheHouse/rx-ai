# RX-AI React Frontend

A modern React-based medical system interface for managing patient data and appointments.

## Features

- 🏥 Patient list view with search functionality
- 📊 Patient cards displaying key information
- 👤 Patient detail view with full visit history
- 🔄 Visit selector to browse between different patient visits
- 💊 Comprehensive visit details (conditions, medications, allergies, issues)
- 📝 Clinical provider notes display
- 🎨 Modern, responsive UI design
- 🔍 Real-time patient search by ID, age, or sex
- 📱 Mobile-friendly responsive layout

## Getting Started

### Prerequisites

- Node.js 16+ and npm installed
- Patient data file from the parent directory

### Installation

1. Install dependencies:
```bash
npm install
```

2. Copy the patient data file to the public directory:
```bash
cp ../data/final_merged_patient_data.json public/data/final_merged_patient_data.json
```

### Development

Start the development server:
```bash
npm run dev
```

The app will open automatically at `http://localhost:3000`

### Build for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## Project Structure

```
react-frontend/
├── public/
│   └── data/              # Patient data files
├── src/
│   ├── components/        # Reusable components
│   │   ├── Header.jsx
│   │   ├── Sidebar.jsx
│   │   ├── Layout.jsx
│   │   └── PatientCard.jsx
│   ├── pages/            # Page components
│   │   └── PatientList.jsx
│   ├── App.jsx           # Main app component
│   ├── App.css           # App styles
│   └── main.jsx          # Entry point
├── index.html
├── vite.config.js
└── package.json
```

## Technology Stack

- **React 18** - UI library
- **React Router 6** - Client-side routing
- **Vite** - Build tool and dev server
- **CSS3** - Styling with Grid and Flexbox

## Next Steps

- ✅ Patient detail view (COMPLETED)
- ✅ Visit selector functionality (COMPLETED)
- Implement patient data editing
- Add authentication
- Connect to a backend API
- Add questionnaire functionality
- Export patient reports
- Add visit comparison feature

