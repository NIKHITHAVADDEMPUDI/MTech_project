import React, { useState } from 'react';
import './App.css';
import axios from 'axios'; // Import Axios for HTTP requests
const backendHost = 'localhost';
const App = () => {
  const [vote, setVote] = useState(null);
  const [name, setName] = useState(''); // To hold the voter's name
  const [error, setError] = useState(null);

  // Handle the vote submission
  const handleVote = (choice) => {
    // Check if name is entered
    if (name.trim() === '') {
      setError('Please enter your name');
      return;
    }

    setVote(choice);
    setError(null); // Clear any previous errors

    // Send the vote along with the name to the backend
    axios
      .post(`http://${backendHost}:30002/vote`, { choice, name })  // Pass the name and choice
      .then((response) => {
        console.log(response.data);
        setError(null);  // Clear any previous errors
      })
      .catch((error) => {
        console.error('There was an error!', error);
        setError('Error: Could not submit vote.');
      });
  };

  return (
    <div className="App">
      <h1 className="header">Voting App</h1>

      <div className="input-container">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Enter your name"
          className="input-name"
        />
      </div>

      <div className="vote-container">
        <p className="vote-text">Vote for your choice:</p>
        <div className="buttons-container">
          <button className="vote-button choice1" onClick={() => handleVote('Choice 1')}>
            Vote for Choice 1
          </button>
          <button className="vote-button choice2" onClick={() => handleVote('Choice 2')}>
            Vote for Choice 2
          </button>
        </div>
      </div>

      {vote && <p className="vote-message">You voted for: {vote}</p>}

      {error && <p className="error-message">{error}</p>}
    </div>
  );
};

export default App;
