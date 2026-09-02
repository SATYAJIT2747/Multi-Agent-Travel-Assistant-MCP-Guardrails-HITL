let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";


/* =========================================
   QUICK PROMPTS
========================================= */

function setPrompt(text) {
    document.getElementById("userInput").value = text;
}


/* =========================================
   LOADING STATE
========================================= */

function setLoading(isLoading) {

    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    sendBtn.disabled = isLoading;

    if (isLoading) {

        btnText.classList.add("hidden");
        btnLoader.classList.remove("hidden");

    } else {

        btnText.classList.remove("hidden");
        btnLoader.classList.add("hidden");
    }
}


/* =========================================
   ERROR HANDLING
========================================= */

function showError(message) {

    const errorBox = document.getElementById("errorBox");

    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}


function hideError() {

    const errorBox = document.getElementById("errorBox");

    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}


/* =========================================
   CREATE PREMIUM TRAVEL CARDS
========================================= */

function createTravelCards(resultBox) {

    // Map AI response sections to icons
    const sectionIcons = {

        "trip summary": "🧳",
        "flight information": "✈️",
        "hotel suggestions": "🏨",
        "day-by-day itinerary": "🗓️",
        "estimated budget": "💰",
        "final recommendations": "💡"
    };


    // Get all main Markdown headings:
    // ## Heading becomes <h2>
    const headings = [
        ...resultBox.querySelectorAll("h2")
    ];


    headings.forEach((heading) => {

        // Remove "1. ", "2. " etc.
        // Convert to lowercase for matching
        const headingText = heading.textContent
            .replace(/^\d+\.\s*/, "")
            .toLowerCase()
            .trim();


        // Default icon
        let icon = "📍";


        // Find the correct icon
        for (const [sectionName, sectionIcon] of Object.entries(sectionIcons)) {

            if (headingText.includes(sectionName)) {

                icon = sectionIcon;
                break;
            }
        }


        // Create the main card
        const card = document.createElement("div");

        card.className = "travel-result-card";


        // Insert the card before the heading
        heading.parentNode.insertBefore(card, heading);


        // Create card header
        const cardHeader = document.createElement("div");

        cardHeader.className = "travel-card-header";


        // Create icon container
        const iconBox = document.createElement("div");

        iconBox.className = "travel-card-icon";
        iconBox.textContent = icon;


        // Add icon to header
        cardHeader.appendChild(iconBox);


        // Move heading into the card header
        cardHeader.appendChild(heading);


        // Add header to card
        card.appendChild(cardHeader);


        /*
        Move all content after this heading
        into the card until we reach
        the next <h2>.
        */

        let nextElement = card.nextSibling;


        while (nextElement) {

            // Stop when the next main section starts
            if (
                nextElement.nodeType === Node.ELEMENT_NODE &&
                nextElement.tagName === "H2"
            ) {
                break;
            }


            // Save the current element
            const currentElement = nextElement;


            // Move pointer before moving element
            nextElement = nextElement.nextSibling;


            // Move content into this card
            card.appendChild(currentElement);
        }

    });
}


/* =========================================
   SHOW AI RESULT
========================================= */

function showResult(answer, threadId) {

    // Save Markdown for PDF generation
    latestAnswerMarkdown = answer;


    const resultSection =
        document.getElementById("resultSection");

    const resultBox =
        document.getElementById("resultBox");

    const threadInfo =
        document.getElementById("threadInfo");


    // Convert Markdown response to HTML
    if (typeof marked !== "undefined") {

        resultBox.innerHTML = marked.parse(answer);

        // Convert major sections into cards
        createTravelCards(resultBox);

    } else {

        // Fallback if Markdown library fails
        resultBox.innerText = answer;
    }


    // Show conversation thread ID
    threadInfo.textContent =
        `Thread ID: ${threadId}`;


    // Make result section visible
    resultSection.classList.remove("hidden");


    // Smoothly scroll to result
    resultSection.scrollIntoView({

        behavior: "smooth",
        block: "start"
    });
}


/* =========================================
   SEND MESSAGE TO FASTAPI
========================================= */

async function sendMessage() {

    hideError();


    const input =
        document.getElementById("userInput");

    const message =
        input.value.trim();


    // Don't send empty messages
    if (!message) {

        showError(
            "Please enter your travel request first."
        );

        return;
    }


    // Show loading spinner
    setLoading(true);


    try {

        // Send POST request to FastAPI
        const response = await fetch(
            "/api/travel",
            {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({

                    message: message,

                    // Send same thread ID for memory
                    thread_id: currentThreadId
                })
            }
        );


        // Convert FastAPI response to JavaScript object
        const data = await response.json();


        // Check for backend errors
        if (!response.ok || !data.success) {

            throw new Error(
                data.error ||
                "Something went wrong."
            );
        }


        // Save thread ID for future requests
        currentThreadId =
            data.thread_id;


        localStorage.setItem(
            "travel_thread_id",
            currentThreadId
        );


        // Display the AI travel plan
        showResult(
            data.answer,
            data.thread_id
        );

    } catch (error) {

        // Show backend/network error
        showError(error.message);

    } finally {

        // Stop loading state
        setLoading(false);
    }
}


/* =========================================
   COPY RESULT
========================================= */

function copyResult() {

    const resultBox =
        document.getElementById("resultBox");

    const text =
        resultBox.innerText;


    // Don't copy if there is no result
    if (!text) {
        return;
    }


    navigator.clipboard.writeText(text)

        .then(() => {

            const copyBtn =
                document.querySelector(".copy-btn");

            const oldText =
                copyBtn.textContent;


            // Temporary success message
            copyBtn.textContent =
                "Copied!";


            setTimeout(() => {

                copyBtn.textContent =
                    oldText;

            }, 1400);
        })


        .catch(() => {

            showError(
                "Could not copy result."
            );
        });
}


/* =========================================
   DOWNLOAD PDF
========================================= */

function downloadPDF() {

    const pdfContent =
        document.getElementById("pdfContent");


    // Check if result exists
    if (!latestAnswerMarkdown || !pdfContent) {

        showError(
            "No travel plan available to download."
        );

        return;
    }


    const downloadBtn =
        document.querySelector(
            ".download-btn"
        );


    const oldText =
        downloadBtn.textContent;


    // Show PDF loading state
    downloadBtn.textContent =
        "Preparing PDF...";

    downloadBtn.disabled =
        true;


    const options = {

        margin: 0.5,

        filename:
            "ai-travel-plan.pdf",


        image: {

            type: "jpeg",

            quality: 0.98
        },


        html2canvas: {

            scale: 2,

            useCORS: true,

            backgroundColor:
                "#ffffff"
        },


        jsPDF: {

            unit: "in",

            format: "a4",

            orientation:
                "portrait"
        },


        pagebreak: {

            mode: [
                "avoid-all",
                "css",
                "legacy"
            ]
        }
    };


    // Generate and download PDF
    html2pdf()

        .set(options)

        .from(pdfContent)

        .save()


        .then(() => {

            // Restore button
            downloadBtn.textContent =
                oldText;

            downloadBtn.disabled =
                false;
        })


        .catch(() => {

            // Restore button on error
            downloadBtn.textContent =
                oldText;

            downloadBtn.disabled =
                false;


            showError(
                "Could not download PDF."
            );
        });
}


/* =========================================
   KEYBOARD SHORTCUT
========================================= */

document.addEventListener(
    "keydown",
    function(event) {

        // Ctrl + Enter sends request
        if (
            event.ctrlKey &&
            event.key === "Enter"
        ) {

            sendMessage();
        }
    }
);