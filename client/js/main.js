function xhr(path, method, onload=null, data=null) {
    const req = new XMLHttpRequest();
    req.addEventListener('load', onload || (() => null));
    req.open(method, `//${window.location.host}/${path}`);
    req.send(data);
}

function fetchUserName() {
    xhr('users', 'GET', (r) => {
        const users = JSON.parse(r.target.responseText);
        for (const user of users) {
            document.querySelector('#user_name').value = user.name;
        }
    });
}

function updateUserName() {
    const userName = document.querySelector('#user_name').value;
    xhr(`users?name=${userName}`, 'POST', reload);
}

function getContext() {
    try {
        return JSON.parse(decodeURIComponent(window.location.hash.slice(1)));
    } catch {
        return {poll: null};
    }
}

function saveContext(poll) {
    window.location.hash = JSON.stringify({poll});
}

function fetchPolls() {
    xhr('polls', 'GET', (r) => {
        const context = getContext();
        const polls = JSON.parse(r.target.responseText);

        const el = document.querySelector('#polls');
        el.textContent = '';

        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.innerText = 'Choose poll';
        el.appendChild(emptyOption);

        for (const poll of polls) {
            const opt = document.createElement('option');
            opt.value = poll.id;
            opt.textContent = poll.name;
            if (poll.id == context.poll) {
                opt.selected = true;
            }
            el.appendChild(opt);
        }
    });
}

function createPoll() {
    const pollName = document.querySelector('#new_poll_name').value;
    xhr(`polls?name=${pollName}`, 'POST', (r) => {
        const poll = r.target.responseText;
        saveContext(poll);
        reload();
    });
}

function onPollChanged() {
    const poll = document.querySelector('#polls').value;
    if (poll) {
        saveContext(poll);
        reload();
    } else {
        saveContext(null);
        reload();
    }
}

function addNewChoice() {
    const context = getContext();
    const choiceName = document.querySelector('#new_choice').value;
    xhr(`choices?poll_id=${context.poll}&name=${choiceName}`, 'POST', reload);
}

function fetchPollResults(poll) {
    xhr(`choices?poll_id=${poll}`, 'GET', (r) => {
        const choices = JSON.parse(r.target.responseText);
        xhr(`votes?poll_id=${poll}`, 'GET', (r) => {
            const votes = JSON.parse(r.target.responseText);
            const votesByChoice = {};
            for (const vote of votes) {
                votesByChoice[vote.choice_id] = vote;
            }
            choices.sort((a, b) => (votesByChoice[b.id]?.vote_count ?? 0) - (votesByChoice[a.id]?.vote_count ?? 0));
            const el = document.querySelector('#choices');
            el.textContent = '';
            for (const choice of choices) {
                const tr = document.createElement('tr');

                const nameTd = document.createElement('td');
                nameTd.textContent = choice.name;
                tr.appendChild(nameTd);

                const votesTd = document.createElement('td');
                const choiceVotes = votesByChoice[choice.id];
                if (choiceVotes) {
                    votesTd.textContent = choiceVotes.vote_count;
                    if (choiceVotes.voted) {
                        votesTd.style.color = 'green';
                    }
                } else {
                    votesTd.textContent = 0;
                }
                tr.appendChild(votesTd);

                const btnTd = document.createElement('td');
                const button = document.createElement('button');
                button.textContent = 'vote';
                button.addEventListener('click', () => vote(choice.id));
                btnTd.appendChild(button);
                tr.appendChild(btnTd);

                el.appendChild(tr);
            }
        });
    });
    fetchVoters(poll);
}

function vote(choiceId) {
    xhr(`votes?choice_id=${choiceId}`, 'POST');
}

function fetchVoters(poll) {
    const el = document.querySelector('#voters');
    xhr(`voters?poll_id=${poll}`, 'GET', (r) => {
        el.textContent = '';
        const voters = JSON.parse(r.target.responseText);
        for (const voter of voters) {
            const li = document.createElement('li');
            li.textContent = voter.name;
            el.appendChild(li);
        }
    });
}

let socket = null;

function reload() {
    fetchUserName();
    fetchPolls();
    const context = getContext();
    fetchPollResults(context.poll);

    if (socket) {
        socket.close();
    }
    if (context.poll) {
        socket = new WebSocket(`ws://${window.location.host}/events?poll_id=${context.poll}`);
        socket.addEventListener('message', reload);
    }
}

(() => {
    document.querySelector('#update_user_name').addEventListener('click', updateUserName)
    document.querySelector('#polls').addEventListener('change', onPollChanged)
    document.querySelector('#save_new_poll').addEventListener('click', createPoll)
    document.querySelector('#add_new_choice').addEventListener('click', addNewChoice);

    reload();
    window.addEventListener('hashchange', reload);
})();
