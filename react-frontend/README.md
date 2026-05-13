# RX-AI React Frontend

A modern React-based medical system interface for managing patient data and appointments.

## Features

### Provider Interface
- 🏥 Patient list view with search functionality
- 📊 Patient cards displaying key information
- 👤 Patient detail view with full visit history
- 🔄 Visit selector to browse between different patient visits
- ✨ **Create new visits** with editable fields for all information
- 💊 Comprehensive visit details (conditions, medications, allergies, issues)
- 📝 Clinical provider notes display and editing
- 🎨 Modern, responsive UI design
- 🔍 Real-time patient search by ID, age, or sex

### 🤖 Dynamic Questionnaire System (Principal Feature)
- **AI-Powered Question Generation** - Contextual questionnaires based on patient data
- **Real-Time Release** - Send questionnaires to patients instantly
- **Live Response Collection** - Auto-populate responses in provider's form
- **Multiple Question Types** - Text, scale, radio, checkbox, multiline
- **Progress Tracking** - Visual feedback for both provider and patient
- **Bi-Directional Communication** - Seamless provider ↔ patient workflow

### Patient Portal
- 📱 Standalone patient interface
- 📋 Real-time questionnaire notifications
- ✍️ Interactive form completion
- ✅ Instant submission to provider
- 🔔 Auto-refresh for new questionnaires

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

### Testing the Questionnaire Workflow

1. **Provider**: Open `http://localhost:3000/patient/P001`
2. Click "+ Create New Visit"
3. Click "Release Questionnaire to Patient"
4. **Patient**: Open `http://localhost:3000/patient-portal/P001` (in new tab)
5. Complete and submit the questionnaire
6. **Provider**: See responses auto-populate!

See the **Testing the Questionnaire Workflow** section above and the root [README.md](../README.md) for API setup.

### Build for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## Project Structure

```
react-frontend/
├── public/
│   └── data/                      # Patient data files
├── src/
│   ├── components/                # Reusable components
│   │   ├── Header.jsx
│   │   ├── Sidebar.jsx
│   │   ├── Layout.jsx
│   │   ├── PatientCard.jsx
│   │   ├── VisitForm.jsx         # Visit creation form
│   │   └── QuestionnaireForm.jsx # Patient questionnaire UI
│   ├── pages/                     # Page components
│   │   ├── PatientList.jsx       # Provider: Patient list
│   │   ├── PatientDetail.jsx     # Provider: Patient detail
│   │   └── PatientView.jsx       # Patient: Portal interface
│   ├── utils/
│   │   └── questionnaireManager.js # Questionnaire state management
│   ├── App.jsx                    # Main app with routing
│   └── main.jsx                   # Entry point
├── index.html
├── vite.config.js
├── package.json
├── README.md
├── QUICKSTART.md
├── CREATE_VISIT_GUIDE.md
├── README.md                      # UI setup; API docs at ../docs/API.md
```

## Technology Stack

- **React 18** - UI library
- **React Router 6** - Client-side routing
- **Vite** - Build tool and dev server
- **CSS3** - Styling with Grid and Flexbox

## Next Steps

### Completed Features ✅
- ✅ Patient list and detail views
- ✅ Visit selector functionality
- ✅ Create new visits with editable fields
- ✅ **Dynamic questionnaire generation workflow**
- ✅ **Patient portal with real-time questionnaires**
- ✅ **Auto-population of questionnaire responses**

### AI integration
- The app calls the FastAPI backend (`/generate-questionnaire`, `/tts`, `/stt`, `/analyze-image`). Configure the API URL in the frontend as needed; default setup expects `http://localhost:8000` with the server running per the root [README.md](../README.md).

### Additional features
- [ ] Edit existing visits
- [ ] Delete visits
- [ ] Authentication & authorization
- [ ] Hardening / realtime (e.g. WebSocket) for live updates beyond current polling
- [ ] Export patient reports (PDF)
- [ ] Visit comparison feature
- [ ] Analytics dashboard
- [ ] Multi-language support

