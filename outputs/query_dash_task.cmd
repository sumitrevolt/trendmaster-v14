@echo off
schtasks /Query /TN "\TrendMaster Live Dashboard" /FO LIST /V > "C:\Users\Ratanshila\Documents\autmated trading\outputs\dash_task_query.txt" 2>&1
