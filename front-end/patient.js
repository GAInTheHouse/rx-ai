document.addEventListener("DOMContentLoaded", () => {
  const notificationArea = document.getElementById("notification-area");

  // In a real application, you would get the userId from a login session.
  // For this demo, we'll just check for any released forms.
  // This checks all localStorage keys to see if any start with 'formReleased_'.
  const formReleased = Object.keys(localStorage).some(
    (key) =>
      key.startsWith("formReleased_") && localStorage.getItem(key) === "true"
  );

  if (formReleased) {
    const userId = Object.keys(localStorage)
      .find(
        (key) =>
          key.startsWith("formReleased_") &&
          localStorage.getItem(key) === "true"
      )
      .split("_")[1];
    notificationArea.innerHTML = `
            <p>A new form is available for you.</p>
            <button onclick="window.location.href='questionnaire.html?userId=${userId}'">Go to Questionnaire</button>
        `;
  }
});
