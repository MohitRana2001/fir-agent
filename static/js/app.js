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

    if (result.extracted_info) {
      updateFormFields(result.extracted_info);
    }
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

function updateFormFields(extractedInfo) {
  const fieldMapping = {
    complainant_name: "complainant_name",
    complainant_address: "complainant_address",
    complainant_phone: "complainant_phone",
    incident_date: "incident_date",
    incident_location: "incident_location",
    nature_of_complaint: "nature_of_complaint",
    incident_description: "incident_description",
    accused_details: "accused_details",
    witnesses: "witnesses",
    property_loss: "property_loss",
    evidence_description: "evidence_description",
  };

  for (const [key, fieldId] of Object.entries(fieldMapping)) {
    if (extractedInfo[key] && extractedInfo[key] !== "null") {
      const field = document.getElementById(fieldId);
      if (field && !field.value.trim()) {
        field.value = extractedInfo[key];
        field.style.backgroundColor = "#e8f5e8";

        // Remove highlighting after 3 seconds
        setTimeout(() => {
          field.style.backgroundColor = "";
        }, 3000);
      }
    }
  }
}

function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
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
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000, // More efficient sample rate for voice
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const pickBestMime = () => {
      const mimes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4;codecs=mp4a.40.2",
        "audio/mp4",
      ];
      return mimes.find((m) => MediaRecorder.isTypeSupported(m)) || "";
    }
    const mimeType = pickBestMime();
    const options = { mimeType, audioBitsPerSecond: 128000 };
    
    mediaRecorder = new MediaRecorder(micStream, options);
    mediaChunks = []; // Clear any previous chunks

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) mediaChunks.push(e.data);
    };
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
          const mime = mediaRecorder.mimeType || "audio/webm";
          const blob = new Blob(mediaChunks, { type: mime });

          const audioUrl = URL.createObjectURL(blob);
          const audioPlayerDiv = document.createElement("div");
          audioPlayerDiv.className = "audio-message";
          audioPlayerDiv.innerHTML = `
            <div class="audio-controls">
              <span class="audio-label">🎵 Your Recording</span>
              <audio controls>
                <source src="${audioUrl}" type="${mime}">
                Your browser does not support the audio element.
              </audio>
            </div>
          `;
          messagesDiv.appendChild(audioPlayerDiv);
          messagesDiv.scrollTop = messagesDiv.scrollHeight;

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

  try {
    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }
  } catch {}
});

async function uploadAudioForTranscription(audioBlob) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "recorded_audio.wav");
  try {
    const resp = await fetch(
      `http://${window.location.host}/transcribe_audio`,
      {
        method: "POST",
        body: formData,
      }
    );
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
      p.textContent = `Transcription failed: ${
        result.message || "Unknown error"
      }`;
      messagesDiv.appendChild(p);
    }
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  } catch (e) {
    const p = document.createElement("p");
    p.className = "system-message";
    p.textContent = "Failed to upload audio for transcription.";
    messagesDiv.appendChild(p);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }
}

const firFormButton = document.getElementById("firFormButton");
const firFormModal = document.getElementById("firFormModal");
const closeFirForm = document.getElementById("closeFirForm");
const cancelFirForm = document.getElementById("cancelFirForm");
const firForm = document.getElementById("firForm");

firFormButton.addEventListener("click", async () => {
  firFormModal.classList.remove("hidden");

  try {
    const resp = await fetch(
      `http://${window.location.host}/get_extracted_info`
    );
    const result = await resp.json();
    if (result.extracted_info) {
      updateFormFields(result.extracted_info);
    }
  } catch (e) {
    console.log("No extracted info available yet");
  }
});

function hideFirForm() {
  firFormModal.classList.add("hidden");
}

closeFirForm.addEventListener("click", hideFirForm);
cancelFirForm.addEventListener("click", hideFirForm);

firFormModal.addEventListener("click", (e) => {
  if (e.target === firFormModal) {
    hideFirForm();
  }
});

firForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = new FormData(firForm);
  const firData = {};

  for (let [key, value] of formData.entries()) {
    firData[key] = value;
  }

  const submitButton = document.getElementById("submitFirForm");
  const originalText = submitButton.textContent;
  submitButton.textContent = "Submitting...";
  submitButton.disabled = true;

  try {
    const response = await fetch(`http://${window.location.host}/submit_fir`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(firData),
    });

    const result = await response.json();

    if (result.success) {
      const successMsg = document.createElement("p");
      successMsg.className = "system-message";
      successMsg.textContent =
        "✅ FIR submitted successfully! The authorities will be in touch.";
      messagesDiv.appendChild(successMsg);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;

      hideFirForm();

      firForm.reset();
    } else {
      alert(`Failed to submit FIR: ${result.message || "Unknown error"}`);
    }
  } catch (error) {
    console.error("Error submitting FIR:", error);
    alert("Failed to submit FIR. Please try again.");
  } finally {
    submitButton.textContent = originalText;
    submitButton.disabled = false;
  }
});
