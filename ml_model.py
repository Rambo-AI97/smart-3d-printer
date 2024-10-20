import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
import numpy as np

# Load the dataset
data = pd.read_csv("print_data.csv")

# Features (input): Temperature, Speed, Layer Height, Infill Percentage
X = data[["Temperature", "Speed", "Layer_Height", "Infill_Percentage"]]
# Target (output): Quality Score
y = data["Quality_Score"]

# Split the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Create a linear regression model
model = LinearRegression()

# Train the model
model.fit(X_train, y_train)

# Test the model on new data
predictions = model.predict(X_test)

# Display predictions and actual results
for i in range(len(predictions)):
    print(f"Predicted Quality: {predictions[i]:.2f}, Actual Quality: {y_test.iloc[i]:.2f}")

# Save the trained model
import joblib
joblib.dump(model, 'ml_model.pkl')
