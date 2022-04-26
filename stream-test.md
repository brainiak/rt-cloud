2. I modified the openNeuroClient.py to download the datasets it runs so it
   could get the appropriate run/subject/task/sessions (the current
   BidsInterface doesn't have a way to directly access methods on the BidsArchive)
3. I modified the data server to download the full dataset and not enforce a run
   be present (as sometimes runs aren't present)
4. Increased timeout for remotable to 15 from 5

Use 'git diff' to see a more granular/precise view of my changes

