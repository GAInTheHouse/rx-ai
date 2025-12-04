document.addEventListener("DOMContentLoaded", () => {
  const questionnaireForm = document.getElementById("questionnaire-form");
  const urlParams = new URLSearchParams(window.location.search);
  const userId = urlParams.get("userId");

  // This is a mock Lambda endpoint. Replace with your actual API Gateway URL.
  const apiUrl = `https://jsonplaceholder.typicode.com/posts?userId=${userId}`;

  fetch(apiUrl)
    .then((response) => response.json())
    .then((questions) => {
      questions.slice(0, 5).forEach((question) => {
        // Limiting to 5 questions for demo
        const questionWrapper = document.createElement("div");
        questionWrapper.classList.add("question");

        const label = document.createElement("label");
        label.textContent = question.title;

        const input = document.createElement("input");
        input.type = "text";
        input.name = `question_${question.id}`;
        input.placeholder = "Your answer here...";

        questionWrapper.appendChild(label);
        questionWrapper.appendChild(input);
        questionnaireForm.appendChild(questionWrapper);
      });

      const submitButton = document.createElement("button");
      submitButton.type = "submit";
      submitButton.textContent = "Submit Answers";
      questionnaireForm.appendChild(submitButton);
    })
    .catch((error) => {
      console.error("Error fetching questionnaire:", error);
      questionnaireForm.innerHTML =
        "<p>Could not load the questionnaire. Please try again later.</p>";
    });

  questionnaireForm.addEventListener("submit", (event) => {
    event.preventDefault();
    alert("Your answers have been submitted. Thank you!");
    // Here you would typically send the form data to your backend

    // Clear the flag in localStorage
    localStorage.removeItem(`formReleased_${userId}`);
    window.location.href = "patient.html";
  });
});
