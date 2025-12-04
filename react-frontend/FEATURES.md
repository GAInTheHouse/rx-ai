# Feature Guide

## Overview

The RX-AI React Frontend provides a comprehensive patient management system for medical professionals.

## Screen Flow

```
┌─────────────────┐
│  Patient List   │  ← Landing Page
│  (Home Screen)  │
└────────┬────────┘
         │
         │ Click on Patient Card
         │
         ▼
┌─────────────────┐
│ Patient Detail  │
│   with Visits   │
└─────────────────┘
```

## 1. Patient List Screen

**Route:** `/`

### Features:
- Grid layout of patient cards
- Search functionality (by ID, age, sex)
- Patient count display
- Quick view of key information per patient

### Patient Card Shows:
- Patient ID
- Visit count badge
- Age, Sex, Height
- Current conditions (up to 3)
- "View Details" button

### User Actions:
- Search/filter patients
- Click any patient card → Navigate to Patient Detail

---

## 2. Patient Detail Screen

**Route:** `/patient/:patientId`

### Navigation:
- "Back to Patients" button returns to list
- URL-based routing (bookmarkable)

### Header Section:
- Large patient ID display
- Demographics summary (Age, Sex, Height)

### Visit Selector:
- Tab-based interface
- Shows all visits for the patient
- Displays visit ID for each
- Active visit highlighted in blue
- Click any tab to view that visit's details

### Visit Details Display:

#### 📊 Four-Column Grid:

1. **🏥 Current Conditions**
   - List of diagnosed conditions
   - Blue left border
   - Hover effects

2. **💊 Medications**
   - List of prescribed medications
   - Green left border
   - Dosage information included

3. **⚠️ Allergies**
   - List of known allergies
   - Red left border
   - Light red background for emphasis

4. **🔍 Issues Detected**
   - List of identified medical issues
   - Yellow left border
   - Risk factors and concerns

#### 📝 Clinical Notes Section:
- Full-width card below the grid
- Complete clinical provider notes
- Professional formatting
- Blue left border accent

### Responsive Design:
- Desktop: 4-column grid
- Tablet: 2-column grid
- Mobile: Single column stack

---

## User Workflows

### Workflow 1: Finding a Patient
1. Land on patient list
2. Use search bar to filter by ID, age, or sex
3. Scan patient cards
4. Click card to view details

### Workflow 2: Reviewing Patient History
1. Open patient detail page
2. See most recent visit by default
3. Click through visit tabs to see historical data
4. Review conditions, medications, allergies
5. Read clinical notes for each visit

### Workflow 3: Comparing Visits
1. Open patient detail
2. Click on earlier visit tab
3. Note the conditions/medications
4. Click on later visit tab
5. Observe changes over time

---

## Design Highlights

### Color Coding:
- **Blue** (#007bff) - Primary actions, conditions
- **Green** (#28a745) - Medications
- **Red** (#dc3545) - Allergies (important alerts)
- **Yellow** (#ffc107) - Issues detected
- **Gray** (#6c757d) - Secondary actions

### Interactive Elements:
- Hover effects on all cards
- Smooth transitions and animations
- Active state indicators
- Click feedback on buttons

### Accessibility:
- Clear visual hierarchy
- High contrast text
- Descriptive icons
- Semantic HTML structure

---

## Technical Details

### State Management:
- React hooks (useState, useEffect)
- Local state per component
- No external state library needed

### Data Flow:
1. Fetch patient data from JSON
2. Filter/search in PatientList
3. Pass patient ID via URL params
4. Load specific patient in PatientDetail
5. Switch visits with local state

### Performance:
- Lazy loading of patient details
- Efficient re-renders with React
- CSS animations via GPU
- Minimal bundle size

---

## Future Enhancements

### Planned Features:
- [ ] Edit patient information
- [ ] Add new visits
- [ ] Questionnaire integration
- [ ] Export patient reports (PDF)
- [ ] Compare visits side-by-side
- [ ] Search within visit notes
- [ ] Filter by condition/medication
- [ ] Timeline view of patient history
- [ ] Charts/graphs for trends
- [ ] Appointment scheduling

### Technical Improvements:
- [ ] Backend API integration
- [ ] Authentication system
- [ ] Real-time updates
- [ ] Offline support
- [ ] Print-friendly views
- [ ] Accessibility audit
- [ ] Unit tests
- [ ] E2E tests

