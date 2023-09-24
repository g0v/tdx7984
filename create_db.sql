create table station (

);

create table stop (
    uid text,
    city text,
    foreign (subroute) references subroute(uid),
    station_id int
    longitude float,
    latitude float
);
