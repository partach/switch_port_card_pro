How run the command line tester:<br>
```snmpwalk -v2c -c public your-switch-ip 1.3.6.1.2.1.2.2.1.2 > textfilesnmpwalkoutput.txt```<br>
```python3 snmp_batch_tester.py textfilesnmpwalkoutput.txt```
