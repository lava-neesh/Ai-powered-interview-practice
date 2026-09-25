/* ================================
   AI Interview Bot - Chatbot JS
   Backend Driven | Clean Version
================================ */

let interviewEnded = false;

/* ---------- INIT ---------- */
window.addEventListener("DOMContentLoaded", () => {
    startInterview();
});

/* ---------- START INTERVIEW ---------- */
function startInterview() {
    setTimeout(fetchQuestion, 1000);
}

/* ---------- FETCH QUESTION ---------- */
function fetchQuestion() {
    fetch("/get-question")
        .then(res => res.json())
        .then(data => {
            if (data.end) {
                interviewEnded = true;
                showInterviewCompleteMessage();
                disableInput();
            }
            else {
                lastQuestionText = data.question;   // ✅ store
                addBotMessage("❓ " + data.question);
                speakText(data.question);
                enableInput();
            }
        })
        .catch(() => {
            addBotMessage("⚠️ Unable to load question. Please try again.");
        });
}

function showInterviewCompleteMessage() {
    const chat = document.getElementById("chatMessages");

    const msg = document.createElement("div");
    msg.className = "message bot";

    const content = document.createElement("div");
    content.className = "message-content";

    const textSpan = document.createElement("span");
    textSpan.innerText = "🎉 You have completed the interview. Thank you!";

    const btn = document.createElement("button");
    btn.innerText = "📊 Check Score";
    btn.className = "check-score-btn";
    btn.style.marginLeft = "12px";
    btn.onclick = () => {
        window.location.href = "/final-result";
    };

    content.appendChild(textSpan);
    content.appendChild(btn);
    msg.appendChild(content);
    chat.appendChild(msg);

    chat.scrollTop = chat.scrollHeight;

    speakText("You have completed the interview. Click check score to view your result.");
}


function replayQuestion() {
    if (!lastQuestionText) {
        addBotMessage("⚠️ No question to replay.");
        return;
    }
    speakText(lastQuestionText);
}

/* ---------- SUBMIT ANSWER ---------- */
function submitAnswer() {
    const input = document.getElementById("answerInput");
    const answer = input.value.trim();
    if (!answer) return;

    addUserMessage(answer);
    input.value = "";
    disableInput();

    fetch("/submit-answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer: answer })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            addBotMessage("⚠️ " + data.error);
            enableInput();
            return;
        }

        if (data.evaluation) {
            addBotMessage(data.evaluation);
        }

        setTimeout(fetchQuestion, 1000);
    })
    .catch(err => {
        console.error(err);
        addBotMessage("⚠️ Server error. Please try again.");
        enableInput();
    });
}


/* ---------- UI HELPERS ---------- */
function addBotMessage(text) {
    const chat = document.getElementById("chatMessages");

    const msg = document.createElement("div");
    msg.className = "message bot";

    const content = document.createElement("div");
    content.className = "message-content";

    // Text span
    const textSpan = document.createElement("span");
    textSpan.innerText = text;

    // Replay button
    const replayBtn = document.createElement("button");
    replayBtn.innerText = "🔊";
    replayBtn.className = "replay-btn";
    replayBtn.onclick = () => speakText(text);

    content.appendChild(textSpan);
    content.appendChild(replayBtn);
    msg.appendChild(content);
    chat.appendChild(msg);

    chat.scrollTop = chat.scrollHeight;

    // Auto speak when message appears
    speakText(text);
}


function addUserMessage(text) {
    const chat = document.getElementById("chatMessages");

    const msg = document.createElement("div");
    msg.className = "message user";

    const content = document.createElement("div");
    content.className = "message-content";
    content.innerText = text;

    msg.appendChild(content);
    chat.appendChild(msg);

    chat.scrollTop = chat.scrollHeight;
}

/* ---------- INPUT CONTROL ---------- */
function disableInput() {
    document.getElementById("answerInput").disabled = true;
    document.getElementById("sendBtn").disabled = true;
}

function enableInput() {
    document.getElementById("answerInput").disabled = false;
    document.getElementById("sendBtn").disabled = false;
    document.getElementById("answerInput").focus();
}

/* ---------- RESET INTERVIEW ---------- */
function resetInterview() {
    fetch("/select-domain-reset")
        .then(() => window.location.href = "/chatbot");
}

/* ---------- ENTER KEY SUBMIT ---------- */
document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && document.activeElement.id === "answerInput") {
        submitAnswer();
    }
});


/* ---------- TEXT TO SPEECH ---------- */
function speakText(text) {
    if (!("speechSynthesis" in window)) {
        console.warn("Speech synthesis not supported");
        return;
    }

    // Stop any previous speech
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 0.95;   // speaking speed
    utterance.pitch = 1.0;   // voice pitch
    utterance.volume = 1.0;  // volume

    window.speechSynthesis.speak(utterance);
}

/* ---------- VOICE INPUT (Speech to Text) ---------- */
let recognition;
let isListening = false;

function toggleVoiceInput() {
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        alert("Voice input is not supported in this browser. Please use Chrome.");
        return;
    }

    if (!recognition) {
        recognition = new SpeechRecognition();
        recognition.lang = "en-US";
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onresult = function (event) {
            const transcript = event.results[0][0].transcript;
            document.getElementById("answerInput").value = transcript;
        };

        recognition.onerror = function (event) {
            console.error("Speech recognition error:", event.error);
            alert("Mic error: " + event.error);
        };

        recognition.onend = function () {
            isListening = false;
            updateMicUI(false);
        };
    }

    if (!isListening) {
        recognition.start();
        isListening = true;
        updateMicUI(true);
    } else {
        recognition.stop();
        isListening = false;
        updateMicUI(false);
    }
}

function updateMicUI(active) {
    const micBtn = document.getElementById("voiceBtn");
    micBtn.innerText = active ? "🎙️ Listening..." : "🎤 Voice";
}
