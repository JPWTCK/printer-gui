async function printFiles(csrfToken) {
    const formData = new URLSearchParams({
        csrfmiddlewaretoken: csrfToken,
    });

    try {
        const response = await fetch('/print_files/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-CSRFToken': csrfToken,
            },
            body: formData,
        });

        if (!response.ok) {
            throw new Error(response.statusText);
        }

        console.log('POST succeeded.');
        window.location.reload(); // Shows the jobs completed message

        window.setTimeout(function() {
            window.location.replace('/'); // Clears out the files listed on screen
        }, 5000);
    } catch (error) {
        console.log('POST failed.');
        alert('The system encountered errors while processing your print jobs.');
        window.location.reload();
    }
}
