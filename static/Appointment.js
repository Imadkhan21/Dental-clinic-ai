function sendMessage(message) {
  fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  })
    .then((res) => res.json())
    .then((botResponse) => {
      console.log("botResponse:", botResponse);

      if (botResponse.action === "show_form") {
        const placeholder = document.createElement("div");
        placeholder.classList.add("bot-message");
        placeholder.innerHTML = "Loading appointment form...";
        chatHistory.appendChild(placeholder);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        // fetch form HTML
        fetch("/get_form")
          .then((res) => res.json())
          .then((data) => {
            placeholder.innerHTML = data.html; // ✅ correct usage
            setupAppointmentForm(placeholder.querySelector("form"));
          })
          .catch((err) => {
            placeholder.innerHTML = "⚠️ Could not load appointment form.";
            console.error(err);
          });
      } else if (botResponse.response) {
        appendBotMessage(botResponse.response);
      } else if (botResponse.error) {
        appendBotMessage(`Error: ${botResponse.error}`);
      }
    })
    .catch((err) => {
      console.error("Send error:", err);
      appendBotMessage(`Error: ${err}`);
    });
}

// === Appointment Form Logic ===
// === Appointment Form Logic ===
async function setupAppointmentForm(formEl) {
  const patientName = formEl.querySelector("[name='patientName']");
  const doctorSelect = formEl.querySelector("[name='doctor']");
  const dateSelect = formEl.querySelector("[name='date']");
  const timeSelect = formEl.querySelector("[name='time']");
  const chatHistory = document.getElementById("chatHistory");

  let doctors = [];
  let minDate = null;

  // === 1. Fetch doctor list from your backend ===
  try {
    const res = await fetch("/api/doctors");
    const data = await res.json();

    if (data.success && data.doctors) {
      doctors = data.doctors;

      doctorSelect.innerHTML = '<option value="">-- Choose Doctor --</option>';
      doctors.forEach((doc) => {
        const opt = document.createElement("option");
        opt.value = doc.id;
        opt.textContent = doc.name;
        doctorSelect.appendChild(opt);
      });
    } else {
      console.error("Failed to fetch doctors:", data.error);
    }
  } catch (err) {
    console.error("Error fetching doctors:", err);
  }

  // === 2. Fetch form info (today’s date) ===
  try {
    const res = await fetch("/get_form");
    const data = await res.json();

    if (data.min_date) {
      minDate = data.min_date;
      dateSelect.setAttribute("min", minDate);
    }
  } catch (err) {
    console.error("Error fetching form metadata:", err);
  }

  // === 3. When doctor changes ===
  doctorSelect.addEventListener("change", () => {
    dateSelect.value = "";
    timeSelect.innerHTML = '<option value="">-- Choose Time --</option>';
  });

  // === 4. When date changes → fetch slots ===
  dateSelect.addEventListener("change", async () => {
    timeSelect.innerHTML = '<option value="">-- Choose Time --</option>';

    const doctorId = doctorSelect.value;
    const selectedDate = dateSelect.value;

    if (!doctorId || !selectedDate) return;

    try {
      const res = await fetch(
        `/get_slots?doctor_id=${doctorId}&date=${selectedDate}`
      );
      const data = await res.json();

      if (data.slots && Array.isArray(data.slots)) {
        data.slots.forEach((slot) => {
          const opt = document.createElement("option");
          opt.value = slot;
          opt.textContent = slot;
          timeSelect.appendChild(opt);
        });
      }
    } catch (err) {
      console.error("Error fetching slots:", err);
    }
  });

  // === 5. Handle form submission ===// === 5. Handle form submission ===
  formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    formEl.parentElement.remove();

    // 🔎 Debugging: log field values before sending
    console.log("Submitting appointment with values:", {
      patient: patientName.value,
      doctor_id: doctorSelect.value,
      doctor_name: doctorSelect.options[doctorSelect.selectedIndex].text,
      date: dateSelect.value,
      time: timeSelect.value,
    });

    try {
      const res = await fetch("/book_appointment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient: patientName.value,
          doctor_id: doctorSelect.value,
          doctor_name: doctorSelect.options[doctorSelect.selectedIndex].text,
          date: dateSelect.value,
          time: timeSelect.value,
        }),
      });

      // 🔎 Debugging: log raw response before parsing
      console.log("Raw response object:", res);

      const data = await res.json();

      // 🔎 Debugging: log parsed JSON
      console.log("Response JSON:", data);

      const confirmation = document.createElement("div");
      confirmation.classList.add("chat-entry", "bot-msg");

      if (data.success) {
        confirmation.innerHTML = `
        <div class="bot-controls">
          <div class="bubble bot">
            ✅ Appointment booked!<br>
            <strong>Patient:</strong> ${patientName.value}<br>
            <strong>Doctor:</strong> ${
              doctorSelect.options[doctorSelect.selectedIndex].text
            }<br>
            <strong>Date:</strong> ${dateSelect.value}<br>
            <strong>Time:</strong> ${timeSelect.value}
          </div>
        </div>
      `;
      } else {
        confirmation.innerHTML = `
        <div class="bot-controls">
          <div class="bubble bot">
            ❌ Could not book appointment: ${data.error}
          </div>
        </div>
      `;
      }

      chatHistory.appendChild(confirmation);
      chatHistory.scrollTop = chatHistory.scrollHeight;
    } catch (err) {
      console.error("❌ Error booking appointment (catch):", err);
      const errorMsg = document.createElement("div");
      errorMsg.classList.add("chat-entry", "bot-msg");
      errorMsg.innerHTML = `
      <div class="bot-controls">
        <div class="bubble bot">
          ❌ Could not book appointment due to a server error.
        </div>
      </div>
    `;
      chatHistory.appendChild(errorMsg);
      chatHistory.scrollTop = chatHistory.scrollHeight;
    }
  });

  // === 6. Handle cancel button ===
  // === 6. Handle cancel button ===
  const cancelBtn = formEl.querySelector(".cancel-btn");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      const parentBubble =
        formEl.closest(".bot-message") || formEl.closest(".chat-entry");
      if (parentBubble) parentBubble.remove();

      const cancelMsg = document.createElement("div");
      cancelMsg.classList.add("chat-entry", "bot-msg");
      cancelMsg.innerHTML = `
      <div class="bot-controls">
        <div class="bubble bot">
          <strong>Bot:</strong> Appointment booking process has been canceled.
        </div>
      </div>
    `;
      chatHistory.appendChild(cancelMsg);
      chatHistory.scrollTop = chatHistory.scrollHeight;
    });
  }
}
