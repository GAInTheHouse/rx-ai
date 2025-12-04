document.addEventListener("DOMContentLoaded", () => {
  const userIdElement = document.getElementById("user-id-title");
  const todoListElement = document.getElementById("todo-list-body");
  const addTodoForm = document.getElementById("add-todo-form");
  const todoTitleInput = document.getElementById("todo-title");

  const urlParams = new URLSearchParams(window.location.search);
  const userId = urlParams.get("userId");

  userIdElement.textContent = `User ${userId}'s Todos`;

  // Fetch and display todos
  fetch(`https://jsonplaceholder.typicode.com/todos?userId=${userId}`)
    .then((response) => response.json())
    .then((todos) => {
      todos.forEach((todo) => {
        const row = document.createElement("tr");
        row.innerHTML = `
                    <td>${todo.id}</td>
                    <td>${todo.title}</td>
                    <td>${todo.completed ? "Completed" : "Pending"}</td>
                `;
        todoListElement.appendChild(row);
      });
    });

  // Handle form submission
  addTodoForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const newTodoTitle = todoTitleInput.value;

    // Here you would typically send this data to your backend (e.g., an API Gateway endpoint that triggers a Lambda)
    // For now, we'll just log it to the console.
    console.log({
      userId: parseInt(userId),
      title: newTodoTitle,
      completed: false,
    });

    alert(
      "New todo added (see console for data). In a real application, this would be saved to the backend."
    );
    todoTitleInput.value = "";
  });
});
