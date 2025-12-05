# Create New Visit Feature Guide

## Overview

Doctors can now create new visits for patients directly from the patient detail screen. Each visit can be fully customized with conditions, medications, allergies, issues detected, and clinical notes.

## How to Use

### Step 1: Navigate to Patient Detail
1. Click on any patient from the patient list
2. You'll see the patient detail page with their visit history

### Step 2: Click "Create New Visit"
1. Find the green **"+ Create New Visit"** button in the top-right corner
2. Click it to open the visit creation form

### Step 3: Fill Out Visit Information

#### 🏥 Conditions
- Type a condition name (e.g., "Type 2 Diabetes")
- Click **"+ Add"** or press **Enter** to add it to the list
- Add multiple conditions as needed
- Click the **×** button to remove any condition

#### 💊 Medications
- Type medication with dosage (e.g., "Metformin 1000mg BID")
- Click **"+ Add"** or press **Enter** to add it
- Add all prescribed medications
- Click the **×** button to remove any medication

#### ⚠️ Allergies
- Type allergy name (e.g., "Penicillin")
- Click **"+ Add"** or press **Enter** to add it
- Add all known allergies
- Click the **×** button to remove any allergy

#### 🔍 Issues Detected
- Type any issues detected (e.g., "Glycemic variability")
- Click **"+ Add"** or press **Enter** to add it
- Add all relevant issues
- Click the **×** button to remove any issue

#### 📝 Clinical Provider Notes
- Type detailed notes about the visit in the text area
- Include observations, treatment plans, and follow-up instructions
- The notes section supports multiple lines

### Step 4: Save or Cancel
- Click **"Save Visit"** to create the new visit
- Click **"Cancel"** to discard changes and close the form

### Step 5: Review New Visit
- After saving, the new visit automatically appears in the visit tabs
- The view automatically switches to show the new visit
- The visit ID is auto-generated (e.g., P001_V3)

## Features

### ✨ Smart Input System
- **Press Enter** to quickly add items without clicking the button
- **Visual feedback** when adding/removing items
- **Smooth animations** for better UX

### 🎨 Color-Coded Items
- **Blue** - Conditions
- **Green** - Medications  
- **Red** - Allergies (with red background for emphasis)
- **Yellow** - Issues detected

### 💾 Data Persistence
- New visits are added to the patient's visit array
- Visit ID is automatically generated
- Data persists during the session
- Ready for backend API integration

### 📱 Responsive Design
- Works perfectly on desktop, tablet, and mobile
- Modal overlay prevents interaction with background
- Scrollable form for smaller screens
- Touch-friendly buttons and inputs

## Visit ID Format

Visit IDs follow this pattern:
```
{PATIENT_ID}_V{VISIT_NUMBER}

Examples:
- P001_V1 (first visit)
- P001_V2 (second visit)
- P001_V3 (third visit)
```

## Workflow Example

### Creating a Follow-Up Visit

1. **Open Patient P001**
   - See existing visits V1 and V2

2. **Click "Create New Visit"**
   - Form opens with Visit ID: P001_V3

3. **Add Conditions:**
   - Type "Type 2 Diabetes" → Add
   - Type "Hypertension" → Add

4. **Add Medications:**
   - Type "Metformin 1000mg BID" → Add
   - Type "Lisinopril 10mg daily" → Add

5. **Add Allergies:**
   - Type "Penicillin" → Add

6. **Add Issues:**
   - Type "Glycemic variability" → Add

7. **Write Notes:**
   ```
   Patient presents for routine follow-up. Reports improved energy 
   levels and better medication compliance. Blood glucose logs show 
   reduced variability. Physical exam unremarkable. Continue current 
   treatment plan. Follow-up in 3 months.
   ```

8. **Click "Save Visit"**
   - Success message appears
   - New visit V3 is created
   - View switches to show V3

## Technical Details

### Form Validation
- Empty inputs are ignored (trimmed before adding)
- Duplicate detection could be added
- All fields are optional except Visit ID

### Data Structure
The form creates a visit object with this structure:
```javascript
{
  visit_id: "P001_V3",
  conditions: ["Type 2 Diabetes", "Hypertension"],
  medications: ["Metformin 1000mg BID", "Lisinopril 10mg daily"],
  allergies: ["Penicillin"],
  issues_detected: ["Glycemic variability"],
  clinical_provider_note: "Patient presents for routine follow-up..."
}
```

### Backend Integration Notes
Currently, the new visit is stored in local component state. To integrate with a backend:

1. Replace the console.log in `handleSaveNewVisit` with an API call:
```javascript
const handleSaveNewVisit = async (newVisitData) => {
  try {
    const response = await fetch(`/api/patients/${patientId}/visits`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newVisitData)
    })
    
    if (response.ok) {
      // Update local state
      const updatedPatient = {
        ...patient,
        visits: [...patient.visits, newVisitData]
      }
      setPatient(updatedPatient)
      setSelectedVisitIndex(updatedPatient.visits.length - 1)
      setShowVisitForm(false)
      alert('Visit saved successfully!')
    }
  } catch (error) {
    console.error('Error saving visit:', error)
    alert('Failed to save visit. Please try again.')
  }
}
```

## Keyboard Shortcuts

- **Enter** - Add item to current field
- **Escape** - Close form (could be added)
- **Tab** - Navigate between fields

## Future Enhancements

Potential improvements:
- [ ] Edit existing visits
- [ ] Delete visits
- [ ] Duplicate previous visit as template
- [ ] Auto-save drafts
- [ ] Form validation with error messages
- [ ] Duplicate item prevention
- [ ] Copy conditions/medications from previous visit
- [ ] Date/time picker for visit
- [ ] Attachment upload (lab results, images)
- [ ] Voice-to-text for notes
- [ ] Templates for common visit types
- [ ] Spell check for medical terms

## Tips for Doctors

### Best Practices
1. **Be Specific** - Include dosages with medications
2. **Be Complete** - List all relevant conditions and allergies
3. **Be Detailed** - Write comprehensive clinical notes
4. **Review Before Saving** - Double-check all information

### Time-Saving Tips
1. Use **Enter key** to quickly add multiple items
2. Write medications with full dosage info
3. Keep notes organized with clear sections
4. Add issues as you identify them during examination

### Common Patterns
- **Chronic Conditions**: Carry over from previous visits
- **Medication Changes**: Note in clinical notes
- **New Allergies**: Highlight in notes when discovered
- **Follow-Up**: Always include next steps in notes

## Troubleshooting

### Form doesn't open
- Ensure you're on the patient detail page
- Check that patient data has loaded

### Can't add items
- Make sure input field is not empty
- Try clicking "Add" button if Enter doesn't work

### Lost data after closing
- Currently, closing the form discards unsaved data
- Always click "Save Visit" to preserve changes

## Support

For issues or feature requests, please contact the development team or check the project documentation.

