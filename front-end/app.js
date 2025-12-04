function releaseForms(userId, button) {
  // Simulate an API call to notify the patient
  console.log(`Notifying user ${userId} about new forms...`);

  button.disabled = true;
  button.textContent = "Releasing...";

  setTimeout(() => {
    // Mock API success
    console.log(`User ${userId} notified.`);
    button.textContent = "Forms Released";

    // Use localStorage to simulate that a form has been released for the patient
    localStorage.setItem(`formReleased_${userId}`, "true");

    alert(`Patient ${userId} has been notified that new forms are available.`);
  }, 1000);
}
document.addEventListener("DOMContentLoaded", () => {
  const userListBody = document.getElementById("user-list-body");

  if (userListBody) {
    fetch("https://jsonplaceholder.typicode.com/users")
      .then((response) => response.json())
      .then((users) => {
        console.log("Fetched users:", users);
        users.forEach((user) => {
          const row = document.createElement("tr");
          const releaseButton = document.createElement("button");
          releaseButton.textContent = "Release Forms";
          releaseButton.onclick = (event) => {
            event.stopPropagation(); // prevent any parent handlers from being executed
            releaseForms(user.id, releaseButton);
          };

          row.innerHTML = `
                        <td>${user.id}</td>
                        <td>${user.name}</td>
                        <td>${user.email}</td>
                        <td></td>
                    `;
          row.cells[3].appendChild(releaseButton);

          // If you still want the row to be clickable to view details:
          row.style.cursor = "pointer";
          row.addEventListener("click", () => {
            window.location.href = `user.html?userId=${user.id}`;
          });

          userListBody.appendChild(row);
        });
      })
      .catch((error) => {
        console.error("Error fetching users:", error);
        if (userListBody) {
          userListBody.innerHTML =
            '<tr><td colspan="4">Could not load user data.</td></tr>';
        }
      });
  } else {
    console.error("Element with ID 'user-list-body' not found.");
  }
});
