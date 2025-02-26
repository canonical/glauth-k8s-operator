INSERT INTO ldapgroups(name, gidnumber) VALUES('superheros', 5502) ON CONFLICT DO NOTHING;
INSERT INTO ldapgroups(name, gidnumber) VALUES('svcaccts', 5503) ON CONFLICT DO NOTHING;
INSERT INTO ldapgroups(name, gidnumber) VALUES('civilians', 5504) ON CONFLICT DO NOTHING;
INSERT INTO ldapgroups(name, gidnumber) VALUES('caped', 5505) ON CONFLICT DO NOTHING;
INSERT INTO ldapgroups(name, gidnumber) VALUES('lovesailing', 5506) ON CONFLICT DO NOTHING;
INSERT INTO ldapgroups(name, gidnumber) VALUES('smoker', 5507) ON CONFLICT DO NOTHING;

INSERT INTO includegroups(parentgroupid, includegroupid) VALUES(5504, 5502) ON CONFLICT DO NOTHING;
INSERT INTO includegroups(parentgroupid, includegroupid) VALUES(5505, 5503) ON CONFLICT DO NOTHING;
INSERT INTO includegroups(parentgroupid, includegroupid) VALUES(5505, 5502) ON CONFLICT DO NOTHING;

INSERT INTO users(name, uidnumber, primarygroup, passsha256) VALUES ('hackers', 5002, 5502, '6478579e37aff45f013e14eeb30b3cc56c72ccdc310123bcdf53e0333e3f416a') ON CONFLICT DO NOTHING;
INSERT INTO users(name, uidnumber, primarygroup, passsha256) VALUES('johndoe', 5003, 5503, '6478579e37aff45f013e14eeb30b3cc56c72ccdc310123bcdf53e0333e3f416a') ON CONFLICT DO NOTHING;
INSERT INTO users(name, mail, uidnumber, primarygroup, passsha256) VALUES('serviceuser', 'serviceuser@example.com', 5004, 5503, '652c7dc687d98c9889304ed2e408c74b611e86a40caa51c4b43f1dd5913c5cd0') ON CONFLICT DO NOTHING;
INSERT INTO users(name, uidnumber, primarygroup, passsha256, othergroups, custattr) VALUES('user4', 5005, 5502, '652c7dc687d98c9889304ed2e408c74b611e86a40caa51c4b43f1dd5913c5cd0', '5505,5506', '{"employeetype":["Intern","Temp"],"employeenumber":[12345,54321]}') ON CONFLICT DO NOTHING;

INSERT INTO capabilities(userid, action, object) VALUES(5002, 'search', 'ou=superheros,dc=glauth,dc=com') ON CONFLICT DO NOTHING;
INSERT INTO capabilities(userid, action, object) VALUES(5004, 'search', '*') ON CONFLICT DO NOTHING;
