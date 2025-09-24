// Test comment
const sessionId = Math.random().toString().substring(10);
const upload_url = "http://" + window.location.host + "/upload/" + sessionId;
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
const attachmentButton = document.getElementById("attachmentButton");
const fileInput = document.getElementById("fileInput");
let is_audio;
document.getElementById("sendButton").disabled = false;
addSubmitHandler();

function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value;
    if (message) {
      const p = document.createElement("p");
      p.className = "user-message";
      p.textContent = message;
      messagesDiv.appendChild(p);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
      messageInput.value = "";
      chatMessage(message);
      console.log("[CLIENT TO AGENT] " + message);
    }
    return false;
  };
}

attachmentButton.addEventListener("click", () => {
  fileInput.click();
});

fileInput.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) {
    uploadFile(file);
  }
  fileInput.value = "";
});

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const p = document.createElement("p");
  p.className = "system-message";
  p.textContent = `Uploading ${file.name}...`;
  messagesDiv.appendChild(p);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;

  try {
    const response = await fetch(upload_url, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) {
      p.textContent = `Error uploading ${file.name}: ${
        result.detail || "Server error"
      }`;
    } else {
      p.textContent = `Successfully uploaded and parsed ${file.name}.`;

      if (result.parsed_content) {
        await chatMessage(
          `I have uploaded a document (${file.name}). Here is the content: ${result.parsed_content}`
        );
      }
    }
  } catch (error) {
    console.error("Error uploading file:", error);
    p.textContent = `Failed to upload ${file.name}.`;
  }
}

async function chatMessage(text) {
  const sendButton = document.getElementById("sendButton");
  sendButton.disabled = true;
  try {
    const resp = await fetch(`http://${window.location.host}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const result = await resp.json();
    const reply = document.createElement("div");
    reply.className = "agent-message";

    const formattedText = formatMarkdown(result.text || "[No response]");
    reply.innerHTML = formattedText;

    messagesDiv.appendChild(reply);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    if (!firFormModal.classList.contains("hidden")) {
        if (result.extracted_info) {
            updateFormFields(result.extracted_info);
        }
    }

    console.log("extracted_info",result);
  } catch (e) {
    const err = document.createElement("p");
    err.className = "agent-message";
    err.textContent = "Error contacting assistant";
    messagesDiv.appendChild(err);
  } finally {
    sendButton.disabled = false;
  }
}

function formatMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/^- (.*$)/gim, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>")
    .replace(/^(.*)$/gim, "<p>$1</p>")
    .replace(/<p><\/p>/g, "")
    .replace(/<p>(<ul>.*<\/ul>)<\/p>/s, "$1");
}

let micStream;
let mediaRecorder;
let mediaChunks = [];
const startAudioButton = document.getElementById("startAudioButton");
const stopAudioButton = document.getElementById("stopAudioButton");

startAudioButton.addEventListener("click", async () => {
  startAudioButton.disabled = true;
  stopAudioButton.disabled = false;
  is_audio = true;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const mimeType = "audio/webm;codecs=opus";
    mediaRecorder = new MediaRecorder(micStream, { mimeType, audioBitsPerSecond: 128000 });
    mediaChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) mediaChunks.push(e.data); };
    mediaRecorder.start();
  } catch (err) {
    console.error("Failed to start recording:", err);
    startAudioButton.disabled = false;
    stopAudioButton.disabled = true;
    is_audio = false;
  }
});

stopAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = false;
  stopAudioButton.disabled = true;
  is_audio = false;
  const p = document.createElement("p");
  p.className = "system-message";
  p.textContent = "Processing audio for transcription...";
  messagesDiv.appendChild(p);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  try {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.onstop = async () => {
        try {
          const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType });
          await uploadAudioForTranscription(blob);
        } catch (e) {
          console.error("Failed to build/upload blob:", e);
        } finally {
          mediaChunks = [];
        }
      };
      mediaRecorder.stop();
    }
  } catch (e) {
    console.error("Error stopping recorder:", e);
  }
  if (micStream) micStream.getTracks().forEach((track) => track.stop());
});

async function uploadAudioForTranscription(audioBlob) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "recorded_audio.webm");
  try {
    const resp = await fetch(`http://${window.location.host}/transcribe_audio`, { method: "POST", body: formData });
    const result = await resp.json();
    const p = document.createElement("p");
    p.className = "system-message";
    if (result.success) {
      p.textContent = "✅ Audio transcribed successfully";
      messagesDiv.appendChild(p);
      if (result.transcription && result.transcription.trim()) {
        await chatMessage(`[Audio Recording] ${result.transcription}`);
      }
    } else {
      p.textContent = `Transcription failed: ${result.message || "Unknown error"}`;
      messagesDiv.appendChild(p);
    }
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  } catch (e) {
    console.error("Failed to upload audio:", e);
  }
}

const firFormButton = document.getElementById("firFormButton");
const firFormModal = document.getElementById("firFormModal");
const closeFirForm = document.getElementById("closeFirForm");
const firFormContainer = document.getElementById("fir-form-container");
let firFormLoaded = false;

firFormButton.addEventListener("click", async () => {
  if (!firFormLoaded) {
    try {
      const response = await fetch("/static/fir_template.html");
      const formHtml = await response.text();
      firFormContainer.innerHTML = formHtml;
      firFormLoaded = true;
      attachFormHandlers();
    } catch (error) {
      console.error("Failed to load FIR form:", error);
      firFormContainer.innerHTML = "<p>Error loading form. Please try again.</p>";
    }
  }
  firFormModal.classList.remove("hidden");
  try {
    const resp = await fetch(`http://${window.location.host}/get_extracted_info`);
    const result = await resp.json();
    setTimeout(() => {
        updateFormFields(result.extracted_info);
      }, 0);
  } catch (e) {
    console.log("No extracted info available yet");
  }
});

function hideFirForm() {
  firFormModal.classList.add("hidden");
}

closeFirForm.addEventListener("click", hideFirForm);

firFormModal.addEventListener("click", (e) => {
  if (e.target === firFormModal) {
    hideFirForm();
  }
});

function updateFormFields(extractedInfo) {
  if (!firFormLoaded) return;
    
  for (const key in extractedInfo) {
    if (key !== 'acts') { 
      const field = document.getElementById(key);
      if (field && extractedInfo[key] && extractedInfo[key] !== "null") {
        if (field.type === 'radio') {
          const radio = document.querySelector(`input[name="${field.name}"][value="${extractedInfo[key]}"]`);
          if (radio) radio.checked = true;
        } else {
          field.value = extractedInfo[key];
        }
      }
    }
  }

  if (extractedInfo.acts && Array.isArray(extractedInfo.acts)) {
    const actsInputContainer = document.getElementById('actsInputContainer');
    if (!actsInputContainer) {
        console.error("actsInputContainer not found in the DOM");
        return;
    }
    actsInputContainer.innerHTML = ''; 

    if (extractedInfo.acts.length === 0) {
      addActSectionRow();
    } else {
      extractedInfo.acts.forEach((actInfo) => {
        addActSectionRow(actInfo.act, actInfo.sections);
      });
    }
  }
}

function attachFormHandlers() {
  const cancelFirForm = document.getElementById("cancelFirForm");
  const submitFirFormButton = document.getElementById("submitFirForm");
  const addActButton = document.getElementById('addActButton');
  const firForm = firFormContainer.querySelector(".contents");
  
  if (cancelFirForm) {
    cancelFirForm.addEventListener("click", hideFirForm);
  }

  if (addActButton) {
    addActButton.addEventListener('click', () => addActSectionRow());
  }
  
  const actsContainer = document.getElementById('actsInputContainer');
  if (actsContainer && actsContainer.childElementCount === 0) {
      addActSectionRow();
  }

  if (submitFirFormButton && firForm) {
    submitFirFormButton.addEventListener('click', async () => {
      // const formP1 = document.getElementById('firFormP1');
      // const formP2 = document.getElementById('firFormP2');
      
      // if (!formP1 || !formP2) {
      //   console.error("One or both form parts are missing!");
      //   alert("Error: Form is not loaded correctly.");
      //   return;
      // }
      
      const formData = new FormData(firForm);
      const firData = {};
      formData.forEach((value, key) => {
        firData[key] = value;
      });

      submitFirFormButton.textContent = "Submitting...";
      submitFirFormButton.disabled = true;

      // const infoType = formP1.querySelector('input[name="infoType"]:checked');
      // if (infoType) firData.infoType = infoType.value;
      
      // const actionTaken = formP2.querySelector('input[name="actionTaken"]:checked');
      // if (actionTaken) firData.actionTaken = actionTaken.value;

      // firData.acts = [];
      // const actInputs = formP1.querySelectorAll('input[name="act[]"]');
      // const sectionInputs = formP1.querySelectorAll('input[name="sections[]"]');
      // actInputs.forEach((actInput, index) => {
      //     const sectionInput = sectionInputs[index];
      //     if (actInput.value || sectionInput.value) {
      //         firData.acts.push({
      //             act: actInput.value,
      //             sections: sectionInput.value
      //         });
      //     }
      // });
      // delete firData['act[]'];
      // delete firData['sections[]'];

      try {
        const response = await fetch(`http://${window.location.host}/submit_fir`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(firData),
        });
        const result = await response.json();
        if (result.success) {
          alert("FIR submitted successfully!");
          hideFirForm();
          firForm.reset();
        } else {
          alert(`Failed to submit FIR: ${result.message || "Unknown error"}`);
        }
      } catch (error) {
        console.error("Error submitting FIR:", error);
        alert("Failed to submit FIR. Please try again.");
      } finally {
        submitFirFormButton.textContent = "Submit FIR";
        submitFirFormButton.disabled = false;
      }
    });
  }
}

function addActSectionRow(actValue = '', sectionsValue = '') {
  const actsInputContainer = document.getElementById('actsInputContainer');
  if (!actsInputContainer) return;

  const rowCount = actsInputContainer.getElementsByClassName('act-group').length;
  const newRow = document.createElement('div');
  newRow.className = 'act-group';
  newRow.style.marginBottom = '10px';
  newRow.style.lineHeight = '24px';

  newRow.innerHTML = `
    <span style="display: inline-block; width: 270px; text-align: right; padding-right: 5px; font-size: 12px; font-family: 'Times New Roman', Times, serif;">(${String.fromCharCode(97 + rowCount)}) Act:</span>
    <input type="text" name="act[]" placeholder="e.g., Indian Penal Code" style="position:static; width:180px;" value="${actValue}">
    <span style="display: inline-block; width: 84px; text-align: right; padding-right: 5px; font-size: 12px; font-family: 'Times New Roman', Times, serif;">Sections:</span>
    <input type="text" name="sections[]" placeholder="e.g., 302, 307" style="position:static; width:280px;" value="${sectionsValue}">
  `;

  if (rowCount > 0) {
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'dynamic-button remove-act-button';
    removeButton.textContent = '- Remove';
    removeButton.addEventListener('click', function() {
      newRow.remove();
      adjustBelowActsContainer();
    });
    newRow.appendChild(removeButton);
  }

  actsInputContainer.appendChild(newRow);
  adjustBelowActsContainer();
}

function adjustBelowActsContainer() {
    const actsInputContainer = document.getElementById('actsInputContainer');
    const belowActsContainer = document.getElementById('below-acts-inputs-container');
    if(actsInputContainer && belowActsContainer) {
        const rowCount = actsInputContainer.getElementsByClassName('act-group').length;
        const newTop = 298 + (rowCount * 34); 
        belowActsContainer.style.top = `${newTop}px`;
    }
}