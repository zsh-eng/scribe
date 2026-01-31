# Scribe
**Scribe** is a web app that aims to make it easier for the public to understand what goes on during Singapore's Parliament sittings. It aggregates data from the [Hansard](https://sprs.parl.gov.sg/search/#/home), which contains the official reports of parliamentary debates, and organises the data from each session into a more user-friendly format.

NOTE: Currently, Scribe only contains data for sittings from the (current) 15th Parliament onwards (September 2025 - present).


## Features
### Cleaner interface for sitting reports
The official Hansard reports are text-only and rather difficult to read. Thus, each sitting's report is broken down into sections, organised by content type, and properly paginated where necessary, allowing the user to view the proceedings in a more digestible manner.

### Categorisation by content type
Broadly speaking, each sitting has three categories of content: questions, bills, and (other) motions. These are each collated into their own respective pages, and users can search through them.

### Categorisation by speaker
Each question, bill, and motion is tagged to their respective speakers. MPs have their own individual page which lists which of these they have spoken on. Users can then use the MP's page to find out more about their involvement in Parliament.

### Categorisation by ministry
Each question, bill, and motion is usually associated with a particular ministry. Thus, where possible, each piece of content is tagged to the ministry. This serves as a proxy for the topic of discussion, and users can thus use each ministry's page to find parliamentary discussions that are related to that ministry and/or topic.

### AI-generated summaries
These are provided for:
- Each section of a sitting
- Each MP's contributions in Parliament (based on their last 20 involvements)

## Tech Stack
### Frontend and Backend
Scribe is written in TypeScript and built using Next.js, with styling done using Tailwind CSS. The database uses PostgreSQL and is hosted on Supabase. Finally, the summaries are generated using Llama 3.1 via Groq's API.

### Data Processing
Data is fetched from the Hansard API, processed, and then inserted into the database using the Python scripts found in the `/python` directory. For more details, please refer to the [`README.md`](/python) there.

Note that the script only works for Hansard data for sittings from ~2012 onwards, as earlier sittings have their data stored in a different format.

## Setup
If you wish to replicate Scribe independently, you can follow the steps below.
1.  **Clone the repository**
    ```bash
    git clone https://github.com/isaacyclai/scribe.git
    cd scribe
    ```

1.  **Install frontend dependencies**
    ```bash
    npm install
    ```

1.  **Setup environment**

    Create an `.env.local` file with your database credentials:
    ```env
    DATABASE_URL=your_database_url
    ```
    If you are using Supabase, you will also need to add your Supabase URL and keys. These can be found by clicking "Connect" on the Supabase dashboard.

1. **Install Python dependencies**
    
    We use `uv` to manage dependencies.
    ```bash
    cd python
    uv sync
    ```

1. **Setup database**

    Dates should be in `DD-MM-YYYY` format.
    ```bash
    uv run batch_process.py <start_date> <end_date>
    ```

1. **(Optional) Generate summaries**
    
    Create an `.env` file with your database URL and Groq API key:
    ```bash
    DATABASE_URL=your_database_url
    GROQ_API_KEY=your_groq_api_key
    ```
    To generate summaries for sessions and members, run the following.
    ```bash
    uv run generate_summaries.py --sessions <start_date> <end_date>
    uv run generate_summaries.py --members
    ```

1.  **Run Development Server**
    ```bash
    npm run dev
    ```
    Open [http://localhost:3000](http://localhost:3000) to view the app.

## Project structure
- `src/app`: Next.js App Router pages and API routes.
- `src/components`: Reusable React components (MemberCard, Pagination, Filters).
- `src/lib`: Utility functions and database connection.
- `python`: Data ingestion and processing scripts.

## Note on summary generation
The choice to use Llama 3.1 via the Groq API was entirely due to its generous API limits (and my lack of credits for other providers' APIs). If you are using this code and would like to use some other API, simply paste your API key into the `.env` file and modify the first few lines of `generate_summaries.py` to set up the OpenAI client with the model and provider of your choice.

## Acknowledgements
This project is inspired by the creators of [Telescope](https://telescope.gov.sg/) and [Pair Search](https://search.pair.gov.sg/).

The copyright to the Hansard is owned by the Singapore Government.