---
title: Paris Pulse
emoji: 🚲
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Vélib' empty-station prediction and a SQL agent
---

# Paris Pulse (DataPilot)

Live demo of DataPilot: watch Vélib' stations empty and refill across a day, see each station's chance of having no bikes in 30 minutes, and ask questions in plain English.

Source code and full write-up: GITHUB_URL

The data is historical (28 October to 5 November 2026), not live. Questions are answered by Gemini on its free tier, so they are limited to a few per hour and may stop for the day. Questions you type are sent to Google.

Data: *Vélib' Métropole station status, every minute (unofficial)*, Angelo Saadeh, https://huggingface.co/datasets/angelosaadeh/velib, from Vélib' Métropole (GBFS) and the Base Adresse Nationale, Licence Ouverte 2.0.
