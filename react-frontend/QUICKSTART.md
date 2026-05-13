# Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Install Dependencies

```bash
cd react-frontend
npm install
```

Or use the setup script:
```bash
./setup.sh
```

### 2. Start the Development Server

```bash
npm run dev
```

The app will automatically open at `http://localhost:3000`

### 3. Start Using the App!

#### Provider Interface (`http://localhost:3000/`)
- Browse all patients
- Search by patient ID, age, or sex
- Click on patient cards to view full details
- Select different visits to see visit-specific information
- **Create new visits** with the "+ Create New Visit" button
- Add/edit conditions, medications, allergies, issues, and notes
- **Release questionnaires to patients** 🤖
- View auto-populated questionnaire responses

#### Patient Portal (`http://localhost:3000/patient-portal/P001`)
- See available questionnaires in real-time
- Complete interactive questionnaires
- Submit responses instantly to provider

### 4. Test the Questionnaire Workflow! 🎯

This is the **main feature** of the project!

1. **Provider:** Open `http://localhost:3000/patient/P001`
2. Click **"+ Create New Visit"**
3. Fill in some basic info (conditions, notes)
4. Scroll to **"Patient Questionnaire"** section
5. Click **"📋 Release Questionnaire to Patient"**
6. **Patient:** Open `http://localhost:3000/patient-portal/P001` in a new tab
7. Click **"Start Questionnaire →"**
8. Fill out all questions
9. Click **"Submit Questionnaire"**
10. **Provider:** Watch responses auto-populate in your form! ✨

See [README.md](./README.md) (Testing the Questionnaire Workflow) and the root [README.md](../README.md) for API setup.

## 📁 Project Structure

```
react-frontend/
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── Header.jsx       # Top navigation bar
│   │   ├── Sidebar.jsx      # Left sidebar navigation
│   │   ├── Layout.jsx       # Page layout wrapper
│   │   └── PatientCard.jsx  # Individual patient card
│   ├── pages/               # Page components
│   │   ├── PatientList.jsx  # Main patient list page
│   │   └── PatientDetail.jsx # Patient detail with visits
│   ├── App.jsx              # Main app with routing
│   └── main.jsx             # Entry point
├── public/
│   └── data/                # Patient data files
└── package.json
```

## 🎨 Features

### Provider Features
✅ Patient list with beautiful card-based UI
✅ Patient detail page with comprehensive visit information
✅ Visit selector to browse patient history
✅ **Create new visits** with full editing capabilities
✅ Add/remove conditions, medications, allergies, and issues
✅ Write and edit clinical provider notes
✅ **🤖 Release AI-generated questionnaires to patients**
✅ **Real-time response collection and auto-population**

### Patient Features
✅ Standalone patient portal interface
✅ Real-time questionnaire notifications
✅ Interactive multi-type questionnaire forms
✅ Progress tracking and validation
✅ Instant submission to provider

### Technical
✅ Real-time search functionality
✅ Responsive design (mobile-friendly)
✅ Modern sidebar navigation
✅ React Router navigation
✅ Clean, maintainable component structure

## 🔜 Next Steps

Here are some features you might want to add:

1. ✅ **Patient Detail View** - COMPLETED! Click on any patient to see full history
2. ✅ **Visit Selection** - COMPLETED! Browse through patient visits
3. ✅ **Create New Visits** - COMPLETED! Doctors can create visits with editable fields
4. **Edit Existing Visits** - Modify previously created visits
5. **Delete Visits** - Remove visits with confirmation
6. **Questionnaire Integration** - Add the questionnaire functionality
7. **Authentication** - Add login for doctors
8. **Backend API** - Connect to a real backend instead of JSON files
9. **Charts & Analytics** - Visualize patient data trends
10. **Appointment Management** - Schedule and track appointments
11. **Visit Comparison** - Compare data across multiple visits side-by-side
12. **Export Reports** - Generate PDF reports for patients

## 🛠️ Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally

## 💡 Tips

- Patient data is loaded from `/public/data/final_merged_patient_data.json`
- All components use modern React hooks (useState, useEffect)
- CSS is modular - each component has its own stylesheet
- The layout uses CSS Grid for responsiveness

Enjoy building! 🎉

