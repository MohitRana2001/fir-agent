/**
 * app.js: JS code for Saathi - Digital FIR Assistant
 */

/**
 * SSE (Server-Sent Events) handling
 */

// Connect the server with SSE
const sessionId = Math.random().toString().substring(10);
const sse_url = "http://" + window.location.host + "/events/" + sessionId;
const send_url = "http://" + window.location.host + "/send/" + sessionId;
let eventSource = null;
let is_audio = false;

// Get DOM elements
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
const connectionStatus = document.getElementById("connectionStatus");
const recordingIndicator = document.getElementById("recordingIndicator");
const uploadButton = document.getElementById("uploadButton");
const fileInput = document.getElementById("fileInput");
let currentMessageId = null;
let formHandlerAdded = false;

// Helper function to safely create lucide icons
function safeCreateIcons() {
  if (typeof lucide !== "undefined" && lucide.createIcons) {
    lucide.createIcons();
  }
}

// Initialize Lucide icons after DOM loads
document.addEventListener("DOMContentLoaded", function () {
  // Wait a bit for lucide to load, then initialize icons
  setTimeout(() => {
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      safeCreateIcons();
      console.log("Lucide icons initialized");
    } else {
      console.warn("Lucide library not loaded");
    }
  }, 100);

  // Initialize file upload
  setupFileUpload();
});

// File upload setup
function setupFileUpload() {
  uploadButton.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", handleFileUpload);
}

// Handle file upload
async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  try {
    uploadButton.disabled = true;
    uploadButton.innerHTML =
      '<i data-lucide="loader-2"></i><span>Uploading...</span>';
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      safeCreateIcons();
    }

    const response = await fetch("/upload_file", {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (result.success) {
      // Add user message showing file upload
      addUserMessage(`📄 Uploaded: ${file.name}`);
    } else {
      console.error("File upload failed:", result.message);
      addSystemMessage("Failed to upload file. Please try again.");
    }
  } catch (error) {
    console.error("Error uploading file:", error);
    addSystemMessage("Error uploading file. Please try again.");
  } finally {
    uploadButton.disabled = false;
    uploadButton.innerHTML =
      '<i data-lucide="paperclip"></i><span>Upload Document</span>';
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      safeCreateIcons();
    }
    fileInput.value = "";
  }
}

// Update connection status
function updateConnectionStatus(status) {
  if (!connectionStatus) {
    console.error("Connection status element not found");
    return;
  }

  const statusIcon = connectionStatus.querySelector("i");
  const statusText = connectionStatus.querySelector("span");

  if (!statusIcon || !statusText) {
    console.error("Status icon or text element not found");
    return;
  }

  connectionStatus.className = `status-indicator ${status}`;

  switch (status) {
    case "connected":
      statusIcon.setAttribute("data-lucide", "wifi");
      statusText.textContent = "Connected";
      break;
    case "connecting":
      statusIcon.setAttribute("data-lucide", "loader-2");
      statusText.textContent = "Connecting...";
      break;
    case "disconnected":
      statusIcon.setAttribute("data-lucide", "wifi-off");
      statusText.textContent = "Disconnected";
      break;
  }

  // Ensure lucide is available before calling createIcons
  if (typeof lucide !== "undefined" && lucide.createIcons) {
    lucide.createIcons();
  } else {
    console.warn("Lucide icons not available");
  }
}

// Add user message
function addUserMessage(text) {
  const messageEl = document.createElement("div");
  messageEl.className = "message-user";
  messageEl.innerHTML = `
    <div class="user-avatar">
      <i data-lucide="user"></i>
    </div>
    <div class="message-content">
      <p>${text}</p>
    </div>
  `;
  messagesDiv.appendChild(messageEl);
  safeCreateIcons();
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Add agent message
function addAgentMessage(text, isPartial = false) {
  if (!currentMessageId || !isPartial) {
    currentMessageId = Math.random().toString(36).substring(7);
    const messageEl = document.createElement("div");
    messageEl.className = "message-agent";
    messageEl.id = currentMessageId;
    messageEl.innerHTML = `
      <div class="agent-avatar">
        <i data-lucide="bot"></i>
      </div>
      <div class="message-content">
        <p></p>
      </div>
    `;
    messagesDiv.appendChild(messageEl);
    lucide.createIcons();
  }

  const messageEl = document.getElementById(currentMessageId);
  const textEl = messageEl.querySelector(".message-content p");

  if (isPartial) {
    textEl.textContent += text;
  } else {
    textEl.textContent = text;
  }

  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Add system message
function addSystemMessage(text) {
  const messageEl = document.createElement("div");
  messageEl.className = "message-agent";
  messageEl.innerHTML = `
    <div class="agent-avatar">
      <i data-lucide="info"></i>
    </div>
    <div class="message-content">
      <p style="color: #6b7280; font-style: italic;">${text}</p>
    </div>
  `;
  messagesDiv.appendChild(messageEl);
  safeCreateIcons();
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// SSE handlers
function connectSSE() {
  updateConnectionStatus("connecting");

  // Connect to SSE endpoint
  eventSource = new EventSource(sse_url + "?is_audio=" + is_audio);

  // Handle connection open
  eventSource.onopen = function () {
    console.log("SSE connection opened.");
    updateConnectionStatus("connected");

    // Add welcome message if this is the first connection
    if (messagesDiv.children.length === 0) {
      const welcomeEl = document.createElement("div");
      welcomeEl.className = "welcome-message";
      welcomeEl.innerHTML = `
        <div class="agent-avatar">
          <i data-lucide="bot"></i>
        </div>
        <div class="message-content">
          <p>Hello, I am <strong>Saathi</strong>, your digital assistant for filing an FIR. I understand this might be a difficult time, and I'm here to help you through the process step-by-step.</p>
        </div>
      `;
      messagesDiv.appendChild(welcomeEl);
      safeCreateIcons();
    }

    // Enable the Send button
    document.getElementById("sendButton").disabled = false;
    if (!formHandlerAdded) {
      addSubmitHandler();
      formHandlerAdded = true;
    }
  };

  // Handle incoming messages
  eventSource.onmessage = function (event) {
    // Parse the incoming message
    const message_from_server = JSON.parse(event.data);
    console.log("[AGENT TO CLIENT] ", message_from_server);

    // Handle error messages
    if (message_from_server.error) {
      updateConnectionStatus("disconnected");
      const errorMsg = message_from_server.message || "Connection error";
      const suggestion = message_from_server.suggestion || "";

      addSystemMessage(
        `❌ ${errorMsg}${suggestion ? "\n💡 " + suggestion : ""}`
      );

      // Show detailed error in console
      console.error("Server error:", message_from_server);
      return;
    }

    // Check if the turn is complete
    if (
      message_from_server.turn_complete &&
      message_from_server.turn_complete == true
    ) {
      currentMessageId = null;
      return;
    }

    // Check for interrupt message
    if (
      message_from_server.interrupted &&
      message_from_server.interrupted === true
    ) {
      // Stop audio playback if it's playing
      if (audioPlayerNode) {
        audioPlayerNode.port.postMessage({ command: "endOfAudio" });
      }
      return;
    }

    // If it's audio, play it
    if (message_from_server.mime_type == "audio/pcm" && audioPlayerNode) {
      audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));
    }

    // If it's a text, print it
    if (message_from_server.mime_type == "text/plain") {
      addAgentMessage(message_from_server.data, true);
    }
  };

  // Handle connection close
  eventSource.onerror = function (event) {
    console.log("SSE connection error or closed.");
    updateConnectionStatus("disconnected");
    document.getElementById("sendButton").disabled = true;
    eventSource.close();
    setTimeout(function () {
      console.log("Reconnecting...");
      connectSSE();
    }, 5000);
  };
}
connectSSE();

// Add submit handler to the form
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (message) {
      addUserMessage(message);
      messageInput.value = "";
      sendMessage({
        mime_type: "text/plain",
        data: message,
      });
      console.log("[CLIENT TO AGENT] " + message);
    }
    return false;
  };
}

// Send a message to the server via HTTP POST
async function sendMessage(message) {
  const isTextMessage = message.mime_type === "text/plain";
  const sendButton = document.getElementById("sendButton");

  if (isTextMessage) {
    sendButton.disabled = true;
  }

  try {
    const response = await fetch(send_url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message),
    });

    if (!response.ok) {
      console.error("Failed to send message:", response.statusText);
    }
  } catch (error) {
    console.error("Error sending message:", error);
  } finally {
    if (isTextMessage) {
      sendButton.disabled = false;
    }
  }
}

// Decode Base64 data to Array
function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Audio handling
 */

let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;

// Audio buffering for 0.2s intervals
let audioBuffer = [];
let bufferTimer = null;

// Import the audio worklets
import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

// Start audio
function startAudio() {
  // Start audio output
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });
  // Start audio input
  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
    }
  );
}

// Start the audio only when the user clicked the button
// (due to the gesture requirement for the Web Audio API)
const startAudioButton = document.getElementById("startAudioButton");
const stopAudioButton = document.getElementById("stopAudioButton");

startAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = true;
  stopAudioButton.disabled = false;
  recordingIndicator.style.display = "flex";
  startAudio();
  is_audio = true;
  eventSource.close(); // close current connection
  connectSSE(); // reconnect with the audio mode
});

stopAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = false;
  stopAudioButton.disabled = true;
  recordingIndicator.style.display = "none";
  stopAudioRecording();
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
  }
  is_audio = false;
  eventSource.close(); // close current connection
  connectSSE(); // reconnect with the audio mode
  addSystemMessage("Transcribing audio...");
});

// Audio recorder handler
function audioRecorderHandler(pcmData) {
  // Add audio data to buffer
  audioBuffer.push(new Uint8Array(pcmData));

  // Start timer if not already running
  if (!bufferTimer) {
    bufferTimer = setInterval(sendBufferedAudio, 200); // 0.2 seconds
  }
}

// Send buffered audio data every 0.2 seconds
function sendBufferedAudio() {
  if (audioBuffer.length === 0) {
    return;
  }

  // Don't send if not in audio mode or no connection
  if (
    !is_audio ||
    !eventSource ||
    eventSource.readyState !== EventSource.OPEN
  ) {
    audioBuffer = []; // Clear buffer if no connection
    return;
  }

  // Calculate total length
  let totalLength = 0;
  for (const chunk of audioBuffer) {
    totalLength += chunk.length;
  }

  // Combine all chunks into a single buffer
  const combinedBuffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of audioBuffer) {
    combinedBuffer.set(chunk, offset);
    offset += chunk.length;
  }

  // Send the combined audio data
  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(combinedBuffer.buffer),
  });
  console.log("[CLIENT TO AGENT] sent %s bytes", combinedBuffer.byteLength);

  // Clear the buffer
  audioBuffer = [];
}

// Stop audio recording and cleanup
function stopAudioRecording() {
  if (bufferTimer) {
    clearInterval(bufferTimer);
    bufferTimer = null;
  }

  // Send any remaining buffered audio only if we have a valid connection
  if (
    audioBuffer.length > 0 &&
    is_audio &&
    eventSource &&
    eventSource.readyState === EventSource.OPEN
  ) {
    sendBufferedAudio();
  } else {
    // Clear buffer if no valid connection
    audioBuffer = [];
  }
}

// Encode an array buffer with Base64
function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}
