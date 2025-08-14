# **Python Focused Editor (PyEdit)**

A minimal yet functional text editor built with Python and PyQt6, specifically designed for Python development.

## **Features**

* **Recent Files**: Quickly access recently opened files.  
* **Font Size Controls**: Easily increase or decrease the editor's font size.  
* **Theme Toggle**: Switch between a light and dark theme.  
* **Session Persistence**: The editor saves and restores open files and their unsaved status on startup.  
* **Duplicate Tab**: A menu item and shortcut (Ctrl+Shift+D) to clone the current tab.  
* **Tab Reordering**: Drag and drop tabs to rearrange them.  
* **Go to Line**: A dialog for quick navigation to a specific line number.  
* **Integrated Debugger**: Run your script with the command-line debugger (pdb).  
* **Stop Script**: Terminate a running script.  
* **Find/Replace**: Advanced dialog for searching and replacing text.  
* **Line Numbers**: Display line numbers for better code navigation.  
* **Close All Tabs**: An action to close all open tabs at once.  
* **Interactive Console**: A dedicated panel for running scripts and interacting with the debugger.  
* **Enhanced Status Bar**: Displays cursor line/column, file type, and modification status.

## **Installation**

### **Prerequisites**

Before you begin, ensure you have the following installed on your system:

1. **Python 3.8+**: You can check your Python version by running python \--version or python3 \--version in your terminal. If you don't have it, you can download it from the official [Python website](https://www.python.org/downloads/).  
2. **Git**: This is required to clone the repository. If you don't have it, you can download it from the official [Git website](https://git-scm.com/downloads).

### **Steps**

1. **Clone the repository**: Open your terminal and run the following commands to download the project files.  
   git clone https://github.com/YourUsername/pyedit.git  
   cd pyedit

2. **Create and activate a virtual environment**: This is a recommended practice to keep your project's dependencies separate from other Python projects.  
   \# Create the virtual environment (named 'venv')  
   python3 \-m venv venv

   \# Activate the virtual environment  
   \# On macOS/Linux:  
   source venv/bin/activate  
   \# On Windows:  
   .\\venv\\Scripts\\activate

3. **Install dependencies**: While the virtual environment is active, install the required libraries using pip.  
   pip install PyQt6

## **Usage**

To run the editor, simply execute the main script from your terminal:

python pyedit.py

## **License**

This project is licensed under the MIT License. See the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.